from logust.contrib import log_fn


@log_fn
def divide(a, b):
    return a / b


divide(10, 2)

try:
    divide(1, 0)
except ZeroDivisionError:
    print("divide() raised, and no timing line was logged")
