import random

import PIL
import keras
import matplotlib
import pygame
from keras import backend as K
import numpy as np
from keras import Input
from keras.engine import Model
from keras.utils import plot_model
from tensorflow.contrib.keras.python.keras import initializers
from tensorflow.contrib.keras.python.keras.layers.convolutional import Conv2D
from tensorflow.contrib.keras.python.keras.layers.core import Activation, Flatten, Dense
import numpy as np
from matplotlib import pyplot as plt


class PlotLosses(keras.callbacks.Callback):

    def __init__(self, game, algorithm):
        self.i = 0
        self.x = []
        self.losses = []
        self.average_losses = []

        self.fig = plt.figure()

        matplotlib.rcParams.update({'font.size': 12})
        self.update_interval = 5000

        self.game = game
        self.algorithm = algorithm
        self.action_names = [x["short"] for x in self.game.players[0].action_space]

    def on_train_begin(self, logs={}):
        pass

    def new_game(self):
        self.i = 0

    def loss_graph(self):
        f = plt.figure(1)
        plt.clf()
        plt.plot(self.x, self.losses, label="loss")
        plt.plot(self.x, self.average_losses, label="average_loss")
        plt.legend()
        f.canvas.draw()
        f.tight_layout()
        wh = f.canvas.get_width_height()
        surf = pygame.image.fromstring(f.canvas.tostring_rgb(), wh, 'RGB')
        self.game.gui.loss_surface = \
            pygame.transform.scale(surf, (int(self.game.gui.game_width / 2), self.game.gui.plot_panel_height))

    def action_distrib_graph(self):
        f = plt.figure(2)
        plt.clf()
        y_pos = np.arange(len(self.algorithm.action_distribution))
        plt.bar(y_pos, self.algorithm.action_distribution, align='center', alpha=0.5)
        plt.xticks(y_pos, self.action_names, fontsize=14)
        plt.ylabel('Frequency')
        plt.title('Action Distribution')
        f.canvas.draw()
        f.tight_layout()
        wh = f.canvas.get_width_height()
        surf = pygame.image.fromstring(f.canvas.tostring_rgb(), wh, 'RGB')
        self.game.gui.action_distribution = \
            pygame.transform.scale(surf, (int(self.game.gui.game_width / 2) + 80, self.game.gui.plot_panel_height))

    def on_epoch_end(self, epoch, logs={}):
        loss = logs.get('loss')

        if len(self.x) <= self.i:
            self.x.append(self.i)
            self.losses.append(0)
            self.average_losses.append(loss)

        self.losses[self.i] = loss
        self.average_losses[self.i] = (self.average_losses[self.i] + loss) / 2

        if self.i % self.update_interval == 0:
            self.loss_graph()
            self.action_distrib_graph()

        self.i += 1


class Memory:

    def __init__(self, memory_size):
        self.buffer = []
        self.count = 0
        self.max_memory_size = memory_size

    def add(self, memory):
        self.buffer.append(memory)
        self.count += 1

        if self.count > self.max_memory_size:
            self.buffer.pop(0)
            self.count -= 1

    def get(self, batch_size=1):
        if self.count <= batch_size:
            return self.buffer

        return random.sample(self.buffer, batch_size)


class Algorithm:

    def __init__(self,
                 game,
                 memory_size=50000,
                 learning_rate=1e-4,
                 epsilon=1.0,
                 epsilon_end=0.10,
                 epsilon_steps=10000,
                 exploration_steps=10000):

        self.game = game
        self.memory = Memory(memory_size)

        self.target_model = None
        self.model = None

        # Static Variables
        self.LEARNING_RATE = learning_rate
        self.EPSILON_START = epsilon
        self.EPSILON_END = epsilon_end
        self.EPSILON_DECAY = (self.EPSILON_END - self.EPSILON_START) / epsilon_steps
        self.EXPLORATION_STEPS = exploration_steps
        self.BATCH_SIZE = 8
        self.GAMMA = 0.99
        self.player = None
        self.state_size = None
        self.action_size = None
        self.state = None
        self.state_vec = None
        self.action_distribution = None

        # Variables
        self.epsilon = self.EPSILON_START
        self.iteration = 0
        self.episode = 0
        self.loss_sum = 0
        self.rewards = 0

        self.plot_losses = PlotLosses(self.game, self)

    def reset(self):
        self.episode += 1
        self.state = np.expand_dims(self.game.get_state(self.player), 0)
        self.plot_losses.new_game()

        if self.target_model:
            self.update_target_model()

    def update_target_model(self):
        # copy weights from model to target_model
        self.target_model.set_weights(self.model.get_weights())

    def init(self):
        self.state = self.game.get_state(self.player)
        self.state_size = self.state.shape

        self.reset()
        self.action_size = len(self.player.action_space)
        self.action_distribution = [0 for _ in range(self.action_size)]

        self.model = self.build_model()
        self.target_model = self.build_model()

        try:
            self.load("./save/dqn_3_p%s.h5" % self.player.id)
            print("Loaded ./save/dqn_3_p%s.h5" % self.player.id)
        except:
            pass

        print("DQNRUnner inited!")
        print("State size is: %s,%s,%s" % self.state_size)
        print("Action size is: %s" % self.action_size)
        print("Batch size is: %s " % self.BATCH_SIZE)

    def build_model(self):
        # Neural Net for Deep-Q learning Model
        initializer = initializers.random_normal(stddev=0.01)

        # Image input
        input_layer = Input(shape=self.state_size, name='image_input')

        conv1 = Conv2D(32, (8, 8), strides=(1, 1), activation='relu', kernel_initializer=initializer)(input_layer)
        conv2 = Conv2D(64, (2, 2), strides=(1, 1), activation='relu', kernel_initializer=initializer)(conv1)
        conv3 = Conv2D(64, (2, 2), strides=(1, 1), activation='relu', kernel_initializer=initializer)(conv2)
        conv_flatten = Flatten()(conv3)

        # Vector state input
        input_layer_2 = Input(shape=(2, ), name="vector_input")
        vec_dense = Dense(128, activation='relu')(input_layer_2)
        concat_layer = keras.layers.Concatenate()([vec_dense, conv_flatten])
        dense_1 = Dense(1024, activation='relu')(concat_layer)

        # Stream split
        fc1 = Dense(512, kernel_initializer=initializer)(dense_1)
        fc2 = Dense(512, kernel_initializer=initializer)(dense_1)

        advantage = Dense(self.action_size)(fc1)
        value = Dense(1)(fc2)

        policy = keras.layers.merge([advantage, value], mode=lambda x: x[0]-K.mean(x[0])+x[1], output_shape=(self.action_size,))

        model = Model(inputs=[input_layer, input_layer_2], outputs=[policy])
        optimizer = keras.optimizers.adam(self.LEARNING_RATE)
        model.compile(optimizer=optimizer, loss='mse')
        plot_model(model, to_file='./model.png', show_shapes=True, show_layer_names=True)

        return model

    def load(self, name):
        self.model.load_weights(name)
        self.target_model.load_weights(name)

    def save(self, name):
        self.target_model.save_weights(name)

    def train(self):
        if self.memory.count < self.BATCH_SIZE:
            return

        loss = 0
        memories = self.memory.get(self.BATCH_SIZE)
        for (s, s_vec, a, r, s1, s1_vec, terminal) in memories:

            target = self.model.predict([s, s_vec])

            if terminal:
                target[0, a] = r
            else:
                pred_a = self.model.predict([s, s_vec])
                pred_t = self.target_model.predict([s1, s1_vec])[0]
                target[0, a] = r + self.GAMMA * pred_t[np.argmax(pred_a)]

            history = self.target_model.fit([s, s_vec], target, epochs=1, batch_size=1, callbacks=[self.plot_losses], verbose=0)
            loss += history.history["loss"][0]

    def act(self):
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)

        # Exploit Q-Knowledge
        act_values = self.target_model.predict([self.state, self.state_vec])
        return np.argmax(act_values[0])  # returns action

    def defense_reward(self):
        #score = 1
        #score -= ((1 - (self.player.health / 50)) * 1.2)
        score = (self.player.health - self.player.opponent.health) / 50


        return score

    def attack_reward(self):
        l_u = len(self.player.units)
        return -1 if l_u <= 0 else l_u

    def update(self, seconds):

        # 1. Do action
        # 2. Observe
        # 3. Train
        # 4. set state+1 to state
        action = self.act()
        self.action_distribution[action] += 1
        s_vec = np.array([[self.player.health, self.player.opponent.health]])
        s, a, s1, r, terminal, _ = self.state, action, *self.game.step(self.player, action)
        s1_vec = np.array([[self.player.health, self.player.opponent.health]])
        s1 = np.expand_dims(s1, 0)

        def_r = self.defense_reward()
        attk_r = self.attack_reward()

        self.memory.add([s, s_vec, a, def_r, s1, s1_vec, terminal])

        self.train()

        self.epsilon += self.EPSILON_DECAY
        self.iteration += 1
        self.state = s1
        self.state_vec = s1_vec
        self.rewards += def_r

        if self.iteration % 100 == 0:
            print("I: %s, Epsilon: %s, def_r: %s, Loss: %s" % (self.iteration, self.epsilon, self.rewards, self.loss_sum / self.iteration))
            self.save("./save/dqn_3_p%s.h5" % self.player.id)