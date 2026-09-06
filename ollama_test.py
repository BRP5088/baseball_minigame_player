"""A deliberately broken scratch file. Not part of the project.

Written 2026-09-06 at the user's request as a test target. Every defect below is
intentional. Do not "fix" it without asking — the errors are the point.
"""


def average(numbers):
    """Mean of a list. Two bugs: divides by the wrong thing, and dies on []."""
    total = 0
    for n in numbers:
        total += n
    return total / len(number)          # NameError: `number` is not defined


def greet(name):
    """Off-by-one on a string index, and a stale variable name."""
    initial = name[len(name)]           # IndexError: last index is len - 1
    return "Hello, " + intial           # NameError: typo, `intial`


def read_count(path):
    """Leaks the handle and compares a str to an int."""
    f = open(path)                      # never closed
    line = f.readline()
    if line > 10:                       # TypeError: str > int
        return "big"
    return "small"


def add_item(item, basket=[]):
    """Mutable default argument — the basket is shared across all calls."""
    basket.append(item)
    return basket


def divide(a, b):
    """No guard on zero."""
    return a / b                        # ZeroDivisionError when b == 0


if __name__ == "__main__":
    print(average([1, 2, 3]))
    print(greet("Brett"))
    print(add_item("apple"))
    print(add_item("pear"))             # returns ['apple', 'pear'], not ['pear']
    print(divide(1, 0))
