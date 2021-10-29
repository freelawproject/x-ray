"""Tools for understanding colors"""

from typing import Tuple


def is_white(color: Tuple[float, float, float]) -> bool:
    """Given an RGB tuple, return True if it's white enough.

    It appears that because PyMuPDF normalizes colorspaces, sometimes you wind
    up with values like:

        (0.9999847412109375, 1.0, 1.0)

    White would be (1, 1, 1), but we get this, presumably because of the
    colorspace converstion. The above example really is white as far as anybody
    can tell, so say so.

    :param color: An RGB tuple representing the color
    :returns True if close to white, else False.
    """
    # White is 1, 1, 1, so 3 minus the sum gives you the whiteness
    rgb_sum = sum(color)
    if rgb_sum < 2.97:
        return False
    return True
