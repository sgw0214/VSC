import numpy as np


def n_size_ndarray_creation(n, dtype=np.int):
    x=np.array([[n,n**2],[n**2,n**2-1]])
    return x
print(n_size_ndarray_creation(3))

def zero_or_one_or_empty_ndarray(shape, type, dtype=np.int):
    if type==0:
        x=np.ndarray(shape).fillna(0)
    elif type==1:
        x=np.ndarray(shape).fillna(1)
    elif type==99:
        x=np.ndarray(shape,order='F')
    return x
zero_or_one_or_empty_ndarray(shape=(2,2), type=1)

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
