import numpy as np


def n_size_ndarray_creation(n, dtype=np.int):
    x=np.arange(n**2).reshape(n,n)
    return x
print(n_size_ndarray_creation(3))

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

def change_shape_of_ndarray(X, n_row):
    x=np.reshape(X,(n_row,-1))
    return x
# print(change_shape_of_ndarray(X, 512))

a = np.array([[1, 2], [3, 4]])
b = np.array([[5, 6]])

def concat_ndarray(X_1, X_2, axis):
    try:
        if X_1.ndim==1: 
            X_1=np.reshape(X_1,(1,-1))
            print(X_1)
        if X_2.ndim==1:
            X_2=np.reshape(X_2,(1,-1))
            print(X_2)
        return np.concatenate((X_1,X_2),axis=axis)
    except ValueError as e:
        return False        
        
# print(concat_ndarray(a, b, 0))

X = np.arange(12, dtype=np.float32).reshape(6,2)

def normalize_ndarray(X, axis=99, dtype=np.float32):
    n_row,n_col=X.shape
    print(n_row)
    if axis==1:
        X_AVG=X.mean(axis=axis).reshape(n_row,-1)
        X_STD=X.std(axis=axis).reshape(n_row,-1)
        
    elif axis==0:
        X_AVG=X.mean(axis=axis).reshape(1,-1)
        X_STD=X.std(axis=axis).reshape(1,-1)

    elif axis==99:
        X_AVG=X.mean()
        X_STD=X.std()
    print(X_AVG,X_STD,(X-X_AVG))
    return (X-X_AVG)/X_STD

# print(normalize_ndarray(X,0))

def save_ndarray(X, filename="test.npy"):
    pass
# X = np.arange(32, dtype=np.float32).reshape(4, -1)
# filename = "test.npy"
# save_ndarray(X, filename)



X = np.arange(32, dtype=np.float32).reshape(4, -1)
# print(X)
def boolean_index(X, condition):
    bi=eval(str("X") + condition)
    bi=np.where(bi)
    return bi

# print(boolean_index(X, "<6"))


def find_nearest_value(X, target_value):
    return X[np.argmin(np.abs(X-target_value))]

X = np.random.uniform(0, 1, 100)
# print(find_nearest_value(X, 0.3))

def get_n_largest_values(X, n):
    return X[np.argsort(X[::-1])[:n]]

X = np.random.uniform(0, 1, 100)
# print(get_n_largest_values(X, 3))