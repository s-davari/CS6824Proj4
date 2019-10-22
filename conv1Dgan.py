'''DCGAN on bioinformatics data using Keras
Author: Frank Wanye, Shakiba Davari
Credit: Rowel Atienza
Project: https://github.com/ShGoldfish/CS6824Proj4
Dependencies: tensorflow 1.0 and keras 2.0
Usage: python3 dcgan_mnist.py
'''

import math
import time

import matplotlib.pyplot as plt
import numpy as np
import scipy.io
# from tensorflow.examples.tutorials.mnist import input_data

from keras.engine.topology import Layer
import keras.backend as K
from keras.models import Sequential
from keras.layers import Dense, Activation, Flatten, Reshape
from keras.layers import Conv1D, Conv2DTranspose, UpSampling1D
from keras.layers import LeakyReLU, Dropout
from keras.layers import BatchNormalization
from keras.layers import Lambda
from keras.optimizers import Adam, RMSprop

class Conv1DTranspose(Layer):
    """Source: https://github.com/tensorflow/tensorflow/issues/6724#issuecomment-357023018
    """
    def __init__(self, filters, kernel_size, strides=1, *args, **kwargs):
        self._filters = filters
        self._kernel_size = (1, kernel_size)
        self._strides = (1, strides)
        self._args, self._kwargs = args, kwargs
        super(Conv1DTranspose, self).__init__()

    def build(self, input_shape):
        print("build", input_shape)
        self._model = Sequential()
        self._model.add(Lambda(lambda x: K.expand_dims(x,axis=1), batch_input_shape=input_shape))
        self._model.add(Conv2DTranspose(self._filters,
                                        kernel_size=self._kernel_size,
                                        strides=self._strides,
                                        *self._args, **self._kwargs))
        self._model.add(Lambda(lambda x: x[:,0]))
        self._model.summary()
        super(Conv1DTranspose, self).build(input_shape)

    def call(self, x):
        return self._model(x)

    def compute_output_shape(self, input_shape):
        return self._model.compute_output_shape(input_shape)

class ElapsedTimer(object):
    def __init__(self):
        self.start_time = time.time()
    def elapsed(self,sec):
        if sec < 60:
            return str(sec) + " sec"
        elif sec < (60 * 60):
            return str(sec / 60) + " min"
        else:
            return str(sec / (60 * 60)) + " hr"
    def elapsed_time(self):
        print("Elapsed: %s " % self.elapsed(time.time() - self.start_time) )

class DCGAN(object):
    def __init__(self, img_rows=28, img_cols=28, channel=1):

        self.img_rows = img_rows
        self.img_cols = img_cols
        self.channel = channel
        self.D = None   # discriminator
        self.G = None   # generator
        self.AM = None  # adversarial model
        self.DM = None  # discriminator model

    # (W−F+2P)/S+1
    def discriminator(self):
        if self.D:
            return self.D
        self.D = Sequential()
        depth = 64
        dropout = 0.4
        # In: 28 x 28 x 1, depth = 1
        # Out: 14 x 14 x 1, depth=64
        input_shape = (self.img_rows, self.channel)
        self.D.add(Conv1D(depth*1, 5, strides=2, input_shape=input_shape, padding='same'))
        self.D.add(LeakyReLU(alpha=0.2))
        self.D.add(Dropout(dropout))

        self.D.add(Conv1D(depth*2, 5, strides=2, padding='same'))
        self.D.add(LeakyReLU(alpha=0.2))
        self.D.add(Dropout(dropout))

        self.D.add(Conv1D(depth*4, 5, strides=2, padding='same'))
        self.D.add(LeakyReLU(alpha=0.2))
        self.D.add(Dropout(dropout))

        self.D.add(Conv1D(depth*8, 5, strides=1, padding='same'))
        self.D.add(LeakyReLU(alpha=0.2))
        self.D.add(Dropout(dropout))

        # Out: 1-dim probability
        self.D.add(Flatten())
        self.D.add(Dense(1))
        self.D.add(Activation('sigmoid'))
        self.D.summary()
        return self.D

    def generator(self):
        if self.G:
            return self.G
        self.G = Sequential()
        dropout = 0.4
        depth = 64 + 64 + 64 + 64  # why is this the depth?
        # dim = 7
        dim = int(self.img_rows / 4)
        # In: 100
        # Out: dim x dim x depth
        self.G.add(Dense(dim*depth, input_dim=100))
        self.G.add(BatchNormalization(momentum=0.9))
        # self.G.add(Activation('relu'))
        self.G.add(Activation('tanh'))
        self.G.add(Reshape((dim, depth)))
        self.G.add(Dropout(dropout))

        # for layer in self.G.layers:
        #     print(type(layer))
        #     print("input: ", layer.input_shape)
        #     print("output: ", layer.output_shape)

        # In: dim x dim x depth
        # Out: 2*dim x 2*dim x depth/2
        self.G.add(UpSampling1D())
        self.G.add(Conv1DTranspose(int(depth/2), 5, padding='same'))
        self.G.add(BatchNormalization(momentum=0.9))
        # self.G.add(Activation('relu'))
        self.G.add(Activation('tanh'))

        self.G.add(UpSampling1D())
        self.G.add(Conv1DTranspose(int(depth/4), 5, padding='same'))
        self.G.add(BatchNormalization(momentum=0.9))
        # self.G.add(Activation('relu'))
        self.G.add(Activation('tanh'))

        self.G.add(Conv1DTranspose(int(depth/8), 5, padding='same'))
        self.G.add(BatchNormalization(momentum=0.9))
        # self.G.add(Activation('relu'))
        self.G.add(Activation('tanh'))

        # Out: 28 x 28 x 1 grayscale image [0.0,1.0] per pix
        self.G.add(Conv1DTranspose(1, 5, padding='same'))
        self.G.add(Activation('linear'))
        self.G.summary()

        return self.G

    def discriminator_model(self):
        if self.DM:
            return self.DM
        optimizer = RMSprop(lr=0.0002, decay=6e-8)
        self.DM = Sequential()
        self.DM.add(self.discriminator())
        self.DM.compile(loss='binary_crossentropy', optimizer=optimizer,\
            metrics=['accuracy'])
        return self.DM

    def adversarial_model(self):
        if self.AM:
            return self.AM
        optimizer = RMSprop(lr=0.0001, decay=3e-8)
        self.AM = Sequential()
        self.AM.add(self.generator())
        self.AM.add(self.discriminator())
        self.AM.compile(loss='binary_crossentropy', optimizer=optimizer,\
            metrics=['accuracy'])
        return self.AM

class CONV1DGAN(object):
    def __init__(self, dataset):
        self.channel = 1
        self.dataset = dataset
        data = scipy.io.loadmat("data/{}.mat".format(dataset))

        # TODO: figure out how to split data into train, valid and test sets
        self.x_train = data['X']
        img_size = math.ceil(self.x_train.shape[1] / 4.0)
        self.img_rows = int(img_size * 4.0)
        self.img_cols = 1
        if self.img_rows != self.x_train.shape[1]:
            self.x_train = np.pad(self.x_train, ((0,0), (0, self.img_rows - self.x_train.shape[1])), 'minimum')
        self.x_train = self.x_train.reshape(self.x_train.shape[0], self.img_rows, 1).astype(np.float32)

        self.DCGAN = DCGAN(self.img_rows, self.img_cols)
        self.discriminator =  self.DCGAN.discriminator_model()
        self.adversarial = self.DCGAN.adversarial_model()
        self.generator = self.DCGAN.generator()

    def train(self, train_steps=2000, batch_size=256, save_interval=0):
        noise_input = None
        if save_interval > 0:
            noise_input = np.random.uniform(-1.0, 1.0, size=[16, 100])
        for i in range(train_steps):
            images_train = self.x_train[np.random.randint(0,
                self.x_train.shape[0], size=batch_size), :, :]
            noise = np.random.uniform(-1.0, 1.0, size=[batch_size, 100])
            images_fake = self.generator.predict(noise)
            x = np.concatenate((images_train, images_fake))
            y = np.ones([2*batch_size, 1])
            y[batch_size:, :] = 0
            d_loss = self.discriminator.train_on_batch(x, y)

            y = np.ones([batch_size, 1])
            noise = np.random.uniform(-1.0, 1.0, size=[batch_size, 100])
            a_loss = self.adversarial.train_on_batch(noise, y)
            log_mesg = "%d: [Discriminator loss: %f, acc: %f]" % (i, d_loss[0], d_loss[1])
            log_mesg = "%s  [Generator loss: %f, acc: %f]" % (log_mesg, a_loss[0], a_loss[1])
            print(log_mesg)
            if save_interval > 0:
                if (i + 1) % save_interval == 0:
                    self.plot_images(save2file=True, samples=noise_input.shape[0], noise=noise_input, step=(i+1))

    def plot_images(self, save2file=False, fake=True, samples=16, noise=None, step=0):
        filename = "{}_{}_real.png".format(self.__class__.__name__, self.dataset)
        if fake:
            filename="{}_{}_fake.png".format(self.__class__.__name__, self.dataset)
            if noise is None:
                noise = np.random.uniform(-1.0, 1.0, size=[samples, 100])
            else:
                filename = "{}_{}_fake_{}.png".format(self.__class__.__name__, self.dataset, step)
            images = self.generator.predict(noise)
        else:
            i = np.random.randint(0, self.x_train.shape[0], samples)
            images = self.x_train[i, :, :]

        plt.figure(figsize=(2, 4))
        # TODO: increase the width of each "image"
        for i in range(images.shape[0]):
            plt.subplot(samples, 1, i+1)
            image = images[i, :, :]
            image = np.reshape(image, [self.img_cols, self.img_rows])
            plt.imshow(image, cmap='gray', aspect='auto')
            plt.axis('off')
        plt.tight_layout()
        if save2file:
            plt.savefig(filename)
            plt.close('all')
        else:
            plt.show()

if __name__ == '__main__':
    mnist_dcgan = CONV1DGAN("ALLAML")
    timer = ElapsedTimer()
    mnist_dcgan.train(train_steps=10, batch_size=1, save_interval=10)
    timer.elapsed_time()
    mnist_dcgan.plot_images(fake=True, save2file=True)
    mnist_dcgan.plot_images(fake=False, save2file=True)