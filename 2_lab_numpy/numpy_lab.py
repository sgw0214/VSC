import numpy as np


def n_size_ndarray_creation(n, dtype=np.int):
    x=np.array([[n,n**2],[n**2,n**2-1]])
    return x
# print(n_size_ndarray_creation(3))

def zero_or_one_or_empty_ndarray(shape, type, dtype=np.int):
    if type==0:
        x=np.ndarray(shape,dtype=dtype)
        x.fill(0)
    elif type==1:
        x=np.ndarray(shape,dtype=dtype)
        x.fill(1)
    elif type==99:
        x=np.ndarray(shape,dtype=dtype)
    return x
# print(zero_or_one_or_empty_ndarray(shape=(23,23), type=1))

X = np.ones((32,32), dtype=np.int)
print(X)
def change_shape_of_ndarray(X, n_row):
    x=np.ndarray(X).reshape(1,-1)
    return x
print(change_shape_of_ndarray(X, 1))

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
