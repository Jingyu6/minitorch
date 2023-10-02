from typing import Tuple

from . import operators
from .autodiff import Context
from .fast_ops import FastOps
from .tensor import Tensor
from .tensor_functions import Function, rand, tensor


def tile(input: Tensor, kernel: Tuple[int, int]) -> Tuple[Tensor, int, int]:
    """
    Reshape an image tensor for 2D pooling

    Args:
        input: batch x channel x height x width
        kernel: height x width of pooling

    Returns:
        Tensor of size batch x channel x new_height x new_width x (kernel_height * kernel_width) as well as the new_height and new_width value.
    """

    batch, channel, height, width = input.shape
    kh, kw = kernel
    assert height % kh == 0
    assert width % kw == 0

    new_height = height // kh
    new_width = width // kw

    # we need to reshape along with each dimension instead of doing
    #   view(batch, channel, new_height, new_width, kh * kw) or 
    #   view(batch, channel, new_height, new_width, kh, kw) or 
    input = input.contiguous().view(
        batch, channel, new_height, kh, new_width, kw
    )
    input = input.permute(0, 1, 2, 4, 3, 5)
    return input.contiguous().view(batch, channel, new_height, new_width, kh * kw), \
        new_height, new_width


def avgpool2d(input: Tensor, kernel: Tuple[int, int]) -> Tensor:
    """
    Tiled average pooling 2D

    Args:
        input : batch x channel x height x width
        kernel : height x width of pooling

    Returns:
        Pooled tensor
    """
    batch, channel, _, _ = input.shape
    tiled_input, new_height, new_width = tile(input, kernel)
    tiled_input = tiled_input.mean(4)
    return tiled_input.contiguous().view(batch, channel, new_height, new_width)


max_reduce = FastOps.reduce(operators.max, -1e9)


def argmax(input: Tensor, dim: int) -> Tensor:
    """
    Compute the argmax as a 1-hot tensor.

    Args:
        input : input tensor
        dim : dimension to apply argmax


    Returns:
        :class:`Tensor` : tensor with 1 on highest cell in dim, 0 otherwise

    """
    out = max_reduce(input, dim)
    return out == input


class Max(Function):
    @staticmethod
    def forward(ctx: Context, input: Tensor, dim: Tensor) -> Tensor:
        "Forward of max should be max reduction"
        ctx.save_for_backward(input, int(dim.item()))
        return max_reduce(input, int(dim.item()))

    @staticmethod
    def backward(ctx: Context, grad_output: Tensor) -> Tuple[Tensor, float]:
        "Backward of max should be argmax (see above)"
        (input_tensor, dim, ) = ctx.saved_values
        argmax_ret = argmax(input_tensor, dim)
        return grad_output * argmax_ret, 0


def max(input: Tensor, dim: int) -> Tensor:
    return Max.apply(input, input._ensure_tensor(dim))


def softmax(input: Tensor, dim: int) -> Tensor:
    r"""
    Compute the softmax as a tensor.



    $z_i = \frac{e^{x_i}}{\sum_i e^{x_i}}$

    Args:
        input : input tensor
        dim : dimension to apply softmax

    Returns:
        softmax tensor
    """
    
    # preserve dimension based on the test
    exp_input = input.exp()
    sum_exp_input = exp_input.sum(dim)
    return (exp_input / sum_exp_input)


def logsoftmax(input: Tensor, dim: int) -> Tensor:
    r"""
    Compute the log of the softmax as a tensor.

    $z_i = x_i - \log \sum_i e^{x_i}$

    See https://en.wikipedia.org/wiki/LogSumExp#log-sum-exp_trick_for_log-domain_calculations

    Args:
        input : input tensor
        dim : dimension to apply log-softmax

    Returns:
         log of softmax tensor
    """
    exp_input = input.exp()
    sum_exp_input = exp_input.sum(dim)
    log_sum_exp_input = sum_exp_input.log()
    return input - log_sum_exp_input


def maxpool2d(input: Tensor, kernel: Tuple[int, int]) -> Tensor:
    """
    Tiled max pooling 2D

    Args:
        input: batch x channel x height x width
        kernel: height x width of pooling

    Returns:
        Tensor : pooled tensor
    """
    batch, channel, _, _ = input.shape
    tiled_input, new_height, new_width = tile(input, kernel)
    tiled_input = max_reduce(tiled_input, 4)
    return tiled_input.contiguous().view(batch, channel, new_height, new_width)


def dropout(input: Tensor, rate: float, ignore: bool = False) -> Tensor:
    """
    Dropout positions based on random noise.

    Args:
        input : input tensor
        rate : probability [0, 1) of dropping out each position
        ignore : skip dropout, i.e. do nothing at all

    Returns:
        tensor with random positions dropped out
    """

    if ignore:
        return input
    else:
        mask = rand(input.shape, input.backend) > rate
        return mask * input

