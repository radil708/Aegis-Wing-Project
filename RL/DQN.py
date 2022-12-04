import random
import numpy as np
import pandas as pd
from operator import add
import collections
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import copy

DEVICE = 'cpu'  # 'cuda' if torch.cuda.is_available() else 'cpu'


class DQNAgent(torch.nn.Module):
    def __init__(self, params):
        super().__init__()
        self.reward = 0
        self.gamma = 0.9
        self.dataframe = pd.DataFrame()
        self.short_memory = np.array([])
        self.agent_target = 1
        self.agent_predict = 0
        self.learning_rate = params['learning_rate']
        self.epsilon = 1
        self.actual = []
        self.first_layer = params['first_layer_size']
        self.second_layer = params['second_layer_size']
        self.third_layer = params['third_layer_size']
        self.memory = collections.deque(maxlen=params['memory_size'])
        self.weights = params['weights_path']
        self.load_weights = params['load_weights']
        self.optimizer = None
        self.network()

    def network(self):
        # Layers
        self.f1 = nn.Linear(11, self.first_layer)
        self.f2 = nn.Linear(self.first_layer, self.second_layer)
        self.f3 = nn.Linear(self.second_layer, self.third_layer)
        self.f4 = nn.Linear(self.third_layer, 3)
        # weights
        if self.load_weights:
            self.model = self.load_state_dict(torch.load(self.weights))
            print("weights loaded")

    def forward(self, x):
        x = F.relu(self.f1(x))
        x = F.relu(self.f2(x))
        x = F.relu(self.f3(x))
        x = F.softmax(self.f4(x), dim=-1)
        return x

    def get_state(self, game, player, food):
        """
        Return the state.
        The state is a numpy array of 11 values, representing:
            - Danger some Agent 1-3 columns to the right and -1,0,1 rows away
            - Danger some Agent 1-2 columns to the left and -1,0,1 rows away
            - Danger same Agent same column and 1-2 rows up or 1 col right/left 2 up.
            - Danger same Agent same column and 1-2 rows down or 1 col right/left 2 down.
            - Danger enemy bullet at same row and 1-3 columns to right
            - Danger enemy bullet at one row up and 1-2 columns to right
            - Danger enemy bullet at one row down and 1-2 columns to right
            - Can move up
            - Can move left
            - Can move right
            - Can move down
            - Player Location
            - Heuristic Enemy Locations board col x board row tensor
            - Counter Enemy Locations
        """
        state = [
            (player.x_change == 20 and player.y_change == 0 and (
                        (list(map(add, player.position[-1], [20, 0])) in player.position) or
                        player.position[-1][0] + 20 >= (game.game_width - 20))) or (
                        player.x_change == -20 and player.y_change == 0 and (
                            (list(map(add, player.position[-1], [-20, 0])) in player.position) or
                            player.position[-1][0] - 20 < 20)) or (player.x_change == 0 and player.y_change == -20 and (
                        (list(map(add, player.position[-1], [0, -20])) in player.position) or
                        player.position[-1][-1] - 20 < 20)) or (player.x_change == 0 and player.y_change == 20 and (
                        (list(map(add, player.position[-1], [0, 20])) in player.position) or
                        player.position[-1][-1] + 20 >= (game.game_height - 20))),  # danger straight

            (player.x_change == 0 and player.y_change == -20 and (
                        (list(map(add, player.position[-1], [20, 0])) in player.position) or
                        player.position[-1][0] + 20 > (game.game_width - 20))) or (
                        player.x_change == 0 and player.y_change == 20 and ((list(map(add, player.position[-1],
                                                                                      [-20, 0])) in player.position) or
                                                                            player.position[-1][0] - 20 < 20)) or (
                        player.x_change == -20 and player.y_change == 0 and ((list(map(
                    add, player.position[-1], [0, -20])) in player.position) or player.position[-1][-1] - 20 < 20)) or (
                        player.x_change == 20 and player.y_change == 0 and (
                        (list(map(add, player.position[-1], [0, 20])) in player.position) or player.position[-1][
                    -1] + 20 >= (game.game_height - 20))),  # danger right

            (player.x_change == 0 and player.y_change == 20 and (
                        (list(map(add, player.position[-1], [20, 0])) in player.position) or
                        player.position[-1][0] + 20 > (game.game_width - 20))) or (
                        player.x_change == 0 and player.y_change == -20 and ((list(map(
                    add, player.position[-1], [-20, 0])) in player.position) or player.position[-1][0] - 20 < 20)) or (
                        player.x_change == 20 and player.y_change == 0 and (
                        (list(map(add, player.position[-1], [0, -20])) in player.position) or player.position[-1][
                    -1] - 20 < 20)) or (
                    player.x_change == -20 and player.y_change == 0 and (
                        (list(map(add, player.position[-1], [0, 20])) in player.position) or
                        player.position[-1][-1] + 20 >= (game.game_height - 20))),  # danger left

            player.x_change == -20,  # move left
            player.x_change == 20,  # move right
            player.y_change == -20,  # move up
            player.y_change == 20,  # move down
            food.x_food < player.x,  # food left
            food.x_food > player.x,  # food right
            food.y_food < player.y,  # food up
            food.y_food > player.y  # food down
        ]

        for i in range(len(state)):
            if state[i]:
                state[i] = 1
            else:
                state[i] = 0

        return np.asarray(state)

    def set_reward(self, player, crash):
        """
        Return the reward.
        The reward is:
            -10 when Snake crashes.
            +10 when Snake eats food
            0 otherwise
        """
        self.reward = 0
        if crash:
            self.reward = -10
            return self.reward
        if player.eaten:
            self.reward = 10
        return self.reward

    def remember(self, state, action, reward, next_state, done):
        """
        Store the <state, action, reward, next_state, is_done> tuple in a
        memory buffer for replay memory.
        """
        self.memory.append((state, action, reward, next_state, done))

    def replay_new(self, memory, batch_size):
        """
        Replay memory.
        """
        if len(memory) > batch_size:
            minibatch = random.sample(memory, batch_size)
        else:
            minibatch = memory
        for state, action, reward, next_state, done in minibatch:
            self.train()
            torch.set_grad_enabled(True)
            target = reward
            next_state_tensor = torch.tensor(np.expand_dims(next_state, 0), dtype=torch.float32).to(DEVICE)
            state_tensor = torch.tensor(np.expand_dims(state, 0), dtype=torch.float32, requires_grad=True).to(DEVICE)
            if not done:
                target = reward + self.gamma * torch.max(self.forward(next_state_tensor)[0])
            output = self.forward(state_tensor)
            target_f = output.clone()
            target_f[0][np.argmax(action)] = target
            target_f.detach()
            self.optimizer.zero_grad()
            loss = F.mse_loss(output, target_f)
            loss.backward()
            self.optimizer.step()

    def train_short_memory(self, state, action, reward, next_state, done):
        """
        Train the DQN agent on the <state, action, reward, next_state, is_done>
        tuple at the current timestep.
        """
        self.train()
        torch.set_grad_enabled(True)
        target = reward
        next_state_tensor = torch.tensor(next_state.reshape((1, 11)), dtype=torch.float32).to(DEVICE)
        state_tensor = torch.tensor(state.reshape((1, 11)), dtype=torch.float32, requires_grad=True).to(DEVICE)
        if not done:
            target = reward + self.gamma * torch.max(self.forward(next_state_tensor[0]))
        output = self.forward(state_tensor)
        target_f = output.clone()
        target_f[0][np.argmax(action)] = target
        target_f.detach()
        self.optimizer.zero_grad()
        loss = F.mse_loss(output, target_f)
        loss.backward()
        self.optimizer.step()