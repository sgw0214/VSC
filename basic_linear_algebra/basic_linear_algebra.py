from typing import Sized


def vector_size_check(*vector_variables):
  return all(len(vector_variables[0])==x for x in [len(vector) for vector in vector_variables[1:]]) 

# print(vector_size_check([1,2,3], [2,3,4], [5,6,7])) # Expected value: True
# print(vector_size_check([1, 3], [2,4], [6,7])) # Expected value: True
# print(vector_size_check([1, 3, 4], [4], [6,7])) # Expected value: False



def vector_addition(*vector_variables):
    if vector_size_check(*vector_variables) == False:
      raise ArithmeticError
    return [sum(x) for x in zip(*vector_variables)]

# print(vector_addition([1, 3], [2, 4], [6, 7])) # Expected value: [9, 14]
# print(vector_addition([1, 5], [10, 4], [4, 7])) # Expected value: [15, 16]
# print(vector_addition([1, 3, 4], [4], [6,7])) # Expected value: ArithmeticError

def vector_subtraction(*vector_variables):
    if vector_size_check(*vector_variables) == False:
      raise ArithmeticError
    return [ x[0]-sum(x[1:]) for x in zip(*vector_variables)]


# print(vector_subtraction([1, 3], [2, 4])) # Expected value: [-1, -1]
# print(vector_subtraction([1, 5], [10, 4], [4, 7])) # Expected value: [-13, -6]

def scalar_vector_product(alpha, vector_variable):
    return [alpha* x for x in vector_variable ]

# print (scalar_vector_product(5,[1,2,3])) # Expected value: [5, 10, 15]
# print (scalar_vector_product(3,[2,2])) # Expected value: [6, 6]
# print (scalar_vector_product(4,[1])) # Expected value: [4]

def matrix_size_check(*matrix_variables):
    return all(len(matrix_variables[0])==len(y) for y in matrix_variables[1:])

# matrix_x = [[2, 2], [2, 2], [2, 2]]
# matrix_y = [[2, 5], [2, 1]]
# matrix_z = [[2, 4], [5, 3]]
# matrix_w = [[2, 5], [1, 1], [2, 2]]
# print (matrix_size_check(matrix_x, matrix_y, matrix_z)) # Expected value: False
# print (matrix_size_check(matrix_y, matrix_z)) # Expected value: True
# print (matrix_size_check(matrix_x, matrix_w)) # Expected value: True

def is_matrix_equal(*matrix_variables):
    return all((matrix_variables[0])==y for y in matrix_variables[1:] )

matrix_x = [[2, 2], [2, 2]]
matrix_y = [[2, 5], [2, 1]]

# print (is_matrix_equal(matrix_x, matrix_y, matrix_y, matrix_y)) # Expected value: False
# print (is_matrix_equal(matrix_x, matrix_x)) # Expected value: True

def matrix_addition(*matrix_variables):
    if matrix_size_check(*matrix_variables) == False:
        raise ArithmeticError
    return [ [sum(y) for y in zip(*x)] for x in zip(*matrix_variables)  ]

matrix_x = [[2, 2], [2, 2]]
matrix_y = [[2, 5], [2, 1]]
matrix_z = [[2, 4], [5, 3]]

# print (matrix_addition(matrix_x, matrix_y)) # Expected value: [[4, 7], [4, 3]]
# print (matrix_addition(matrix_x, matrix_y, matrix_z)) # Expected value: [[6, 11], [9, 6]]

def matrix_subtraction(*matrix_variables):
    if matrix_size_check(*matrix_variables) == False:
        raise ArithmeticError
    print([k[0] for k in zip(*matrix_variables)-([sum(y) for y in zip(*x)] for x in zip(*matrix_variables[1:]))])
    return None

# ()
matrix_x = [[2, 2], [2, 2]]
matrix_y = [[2, 5], [2, 1]]
matrix_z = [[2, 4], [5, 3]]

# print (matrix_subtraction(matrix_x, matrix_y)) # Expected value: [[0, -3], [0, 1]]
print (matrix_subtraction(matrix_x, matrix_y, matrix_z)) # Expected value: [[-2, -7], [-5, -2]]

def matrix_transpose(matrix_variable):
    return None


def scalar_matrix_product(alpha, matrix_variable):
    return None


def is_product_availability_matrix(matrix_a, matrix_b):
    return None


def matrix_product(matrix_a, matrix_b):
    if is_product_availability_matrix(matrix_a, matrix_b) == False:
        raise ArithmeticError
    return None
