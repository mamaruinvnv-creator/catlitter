"""A deliberately messy module used by the test-suite."""
import os  # unused-import
import json
from sys import argv  # unused-import
from utils import shared_util

USED_CONST = 42


def helper(x):  # used in main -> keep
    return x + 1


def dead_function():  # unused anywhere in the project -> waste
    return 123


class DeadClass:  # unused anywhere -> waste
    pass


class AliveClass:  # referenced in main -> keep
    def run(self):
        return json.dumps({"ok": True})


def duplicate():
    return 1


def duplicate():  # duplicate-definition -> waste
    return 2


def empty_one():
    """an empty stub"""
    pass


def flow(values):
    total = 0
    unused_local = 999
    for v in values:
        total += v
    return total


def unreachable_demo():
    return 1
    print("this can never run")


# def old_feature(a):
#     result = a + 1
#     return result


def main():
    print(helper(USED_CONST))
    print(AliveClass().run())
    print(shared_util())
    flow([1, 2])


if __name__ == "__main__":
    main()
