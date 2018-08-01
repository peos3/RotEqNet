import torch.nn as nn


class Flatten(nn.Module):
    def forward(self, input):
        print(input.size())
        return input.view(input.size(0), -1)