# Global imports
import torch
import torch.nn as nn
from torch.nn import functional as F
from PIL import Image
from torch import optim
import numpy as np
from torch.autograd import Variable
import random
from torchvision import transforms
import os
import math
import matplotlib.pyplot as plt
import sys

# Local imports
# Layers
from framework.layers import RotConv
from framework.layers import VectorUpsample
from framework.layers import VectorToMagnitude
from framework.layers import VectorBatchNorm
from framework.layers import SpatialPooling
from framework.layers import OrientationPooling
from framework.loss import F1Loss, Angle_Loss
# Utils
from framework.utils.utils import *

"""
An implementation to detect Dung Beetles and their orientation based on the concept proposed in:
Rotation equivariant vector field networks (ICCV 2017)
Diego Marcos, Michele Volpi, Nikos Komodakis, Devis Tuia
https://arxiv.org/abs/1612.09346
https://github.com/dmarcosg/RotEqNet
"""

if __name__ == '__main__':
    # Define network
    class Net(nn.Module):
        def __init__(self):
            super(Net, self).__init__()
            filter_size = 9

            self.main = nn.Sequential(
                # 300x400
                RotConv(1, 4, [filter_size, filter_size], 1, filter_size // 2, n_angles=17, mode=1),
                OrientationPooling(),
                VectorBatchNorm(4),
                SpatialPooling(2),

                # 150x200
                RotConv(4, 8, [filter_size, filter_size], 1, filter_size // 2, n_angles=17, mode=2),
                OrientationPooling(),
                VectorBatchNorm(8),
                SpatialPooling(2),

                # 75x100
                RotConv(8, 4, [filter_size, filter_size], 1, filter_size // 2, n_angles=17, mode=2),
                OrientationPooling(),
                VectorBatchNorm(4),
                VectorUpsample(scale_factor=2),

                # 150x200
                RotConv(4, 2, [filter_size, filter_size], 1, filter_size // 2, n_angles=17, mode=2),
                OrientationPooling(),
                VectorBatchNorm(2),
                VectorUpsample(size=img_size),

                # 300x400
                RotConv(2, 1, [filter_size, filter_size], 1, filter_size // 2, n_angles=17, mode=2),
                OrientationPooling(),

                RotConv(1, 1, [filter_size, filter_size], 1, filter_size // 2, n_angles=17, mode=2),
                OrientationPooling(),

                VectorToMagnitude(0.99999)
            )

        def forward(self, x):
            x = self.main(x)
            # magnitude
            y = F.relu(x[0])
            # angle
            z = F.relu6(x[1])
            return (y, z)


    def adjust_learning_rate(optimizer, epoch):
        """
        Gradually decay learning rate"
        NOTE: Will be used in future implementation
        :param optimizer: optimizer which should be used
        :param epoch: current number of training epoch
        """""
        if epoch == 4:
            lr = start_lr / 10
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr
        if epoch == 6:
            lr = start_lr / 100
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr
        if epoch == 8:
            lr = start_lr / 100
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr


    def getBatch(dataset):
        """ Collect a batch of samples from list """
        # Make batch
        data = []
        labels = []
        for sample_no in range(batch_size):
            tmp = dataset.pop()  # Get top element and remove from list
            img = tmp[0].astype('float32').squeeze()
            data.append(np.expand_dims(img, 0))
            labels.append(tmp[1].squeeze())
        data = np.concatenate(data, 0)
        labels = np.array(labels, 'float32')

        data = Variable(torch.from_numpy(data))
        labels = Variable(torch.from_numpy(labels))

        if type(gpu_no) == int:
            data = data.cuda(gpu_no)
            labels = labels.cuda(gpu_no)
        return data, labels


    def load_data(train, test):
        # trainfiles
        imgs = np.load(base_folder + train + "/" + train + "_input.npz")['data']
        for i in range(len(imgs)):
            imgs[i] = imgs[i] / 255 - 0.5

        np.swapaxes(imgs, 0, 1)
        mask_data = np.load(base_folder + train + "/" + train + "_masks.npz")['beetle']
        for i in range(len(mask_data)):
            mask_data[i][1] = mask_data[i][1] * math.pi / 180
        train = list(zip(imgs, mask_data))

        # testfiles
        imgs = np.load(base_folder + test + "/" + test + "_input.npz")['data']
        for i in range(len(imgs)):
            imgs[i] = imgs[i] / 255 - 0.5

        mask_data = np.load(base_folder + test + "/" + test + "_masks.npz")['beetle']
        for i in range(len(mask_data)):
            mask_data[i][1] = mask_data[i][1] * math.pi / 180
        test = list(zip(imgs, mask_data))

        # Temporary workaround to split data into train and test
        first_rand = 30  # randint(0, len(imgs)-1)
        second_rand = 42  # randint(0, len(imgs)-1)

        test = list(zip([imgs[first_rand], imgs[second_rand]], [mask_data[first_rand], mask_data[second_rand]]))
        np.delete(imgs, first_rand)
        np.delete(imgs, second_rand)

        train = list(zip(imgs, mask_data))

        return train, train, test


    def train(net):
        # Net Parameters
        if type(gpu_no) == int:
            net.cuda(gpu_no)

        optimizer = optim.Adam(net.parameters(), lr=start_lr)  # , weight_decay=0.01)

        for epoch_no in range(epoch_size):

            # Random order for each epoch
            train_set_for_epoch = train_set[:]   # Make a copy
            random.shuffle(train_set_for_epoch)  # Shuffle the copy

            # Training
            net.train()
            for batch_no in range(len(train_set) // batch_size):

                # Train
                optimizer.zero_grad()

                data, labels = getBatch(train_set_for_epoch)
                out1, out2 = net(data)
                loss1 = criterion1(out1.squeeze(1), labels[:, 0, :, :])
                loss2 = criterion2(out2.squeeze(1), labels[:, 1, :, :])
                loss = loss1 + loss2 / (2 * math.pi)
                loss.backward()

                optimizer.step()

                # Print training-acc
                if batch_no % 10 == 0:
                    print('Train', 'epoch:', epoch_no,
                          ' batch:', batch_no,
                          ' loss:', loss.data.cpu().numpy(),
                          ' loss1:', loss1.data.cpu().numpy(),
                          ' loss2:', loss2.data.cpu().numpy(),
                          )

            adjust_learning_rate(optimizer, epoch_no)
            torch.save(net.state_dict(), os.path.join(models_folder, model_file))


    def load(net):
        net.load_state_dict(torch.load(os.path.join(models_folder, model_file)))
        if type(gpu_no) == int:
            net.cuda()


    def test(net):
        net.eval()
        loader = transforms.Compose([transforms.ToTensor()])
        image = loader(np.expand_dims(test_set[test_image][0][0], 2)).float()
        image = image.cuda()
        xyz = net(image)
        magnitude = xyz[0].data.cpu().numpy().squeeze(0).squeeze(0)
        magnitude = np.squeeze(magnitude)
        angles = xyz[1].data.cpu().numpy().squeeze(0).squeeze(0)

        orig = Image.fromarray((test_set[test_image][0][0] + 0.5) * 255)
        orig.show(title='orig')

        mag = Image.fromarray(((magnitude) * 255))
        mag.show(title='net')

        # Heatmap and Angle Map visualization
        fig, ax = plt.subplots()
        im = ax.imshow(magnitude)

        def pol2cart(magnitude_map, angle_map):
            # This is equivalent to switching u and v in the quiver function
            angle_map_zero_up = ((2 * math.pi - angle_map) + 0.5 * math.pi) % (2 * math.pi)
            u = magnitude_map * np.cos(angle_map_zero_up)
            v = magnitude_map * np.sin(angle_map_zero_up)
            return u, v

        def xy_coords():
            x_single_col = np.array(list(range(0, img_size[1])))
            y_single_row = np.array(list(range(0, img_size[0])))

            x = np.tile(x_single_col, (img_size[0], 1))
            y = np.tile(y_single_row, (img_size[1], 1))
            y = y.transpose()

            return x, y

        magnitude[magnitude < thresh] = 0
        (u, v) = pol2cart(magnitude, angles)
        (x, y) = xy_coords()

        ax.quiver(x, y, u, v, color='w')
        fig.colorbar(im)
        ax.set(aspect=1, title='Heatmap and Anglemap')
        plt.show()


    # ------MAIN------
    # Load datasets
    img_size = (300, 400)
    base_folder = "./data/"
    models_folder = "./models"
    # workaround
    if not os.path.isdir(base_folder):
        base_folder = "." + base_folder
        models_folder = "." + models_folder
    train_file = "Allogymnopleuri_#05"  # to choose all -> "combined"
    test_file = "Allogymnopleuri_#05"
    train_set, val_set, test_set = load_data(train_file, test_file)
    model_file = train_file + "_model.pt"
    if (len(sys.argv) == 4):
        model_file = train_file + "_" + sys.argv[3] + ".pt"

    # Setup net, loss function, optimizer and hyper parameters
    start_lr = 0.01
    epoch_size = 3
    if (len(sys.argv) > 2 and sys.argv[1] == "train"):
        epoch_size = (int)(sys.argv[2])
    batch_size = 10
    test_image = 70
    if (len(sys.argv) > 2 and sys.argv[1] == "test"):
        test_image = (int)(sys.argv[2])
    # magnitude
    criterion1 = F1Loss()
    # angle
    criterion2 = Angle_Loss()
    net = Net()
    gpu_no = 0  # Set to False for cpu-version

    # Magnitude Threshold param
    thresh = 0.8

    if (len(sys.argv) == 1):
        train(net)
        test(net)
    elif (sys.argv[1] == "train"):
        train(net)
    elif (sys.argv[1] == "test"):
        load(net)
        test(net)
