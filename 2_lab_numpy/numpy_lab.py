import numpy as np


def n_size_ndarray_creation(n, dtype=np.int):
    k=np.array([[n,n**2],[n**2,n**2-1]])
    return k
print(n_size_ndarray_creation(3))

def zero_or_one_or_empty_ndarray(shape, type=0, dtype=np.int):
    pass


def change_shape_of_ndarray(X, n_row):
    pass


def concat_ndarray(X_1, X_2, axis):
    pass


def normalize_ndarray(X, axis=99, dtype=np.float32):
    pass


def save_ndarray(X, filename="test.npy"):
    pass


def boolean_index(X, condition):
    pass


def find_nearest_value(X, target_value):
    pass


def get_n_largest_values(X, n):
    pass