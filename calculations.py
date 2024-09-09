
'''
      A 3*3 window with numbered cells. 
      The number in the cell is to identify each cell in presented equations, and the fxand fy represent 
      the x and y perpendicular gradients
         0   1   2
      0 [z9, z8, z7]
      1 [z6, z5, z4]
      2 [z3, z2, z1]

      https://journals.vilniustech.lt/index.php/GAC/article/view/4060/3445

'''
import math

class _3x3WindowMatrix():
      def __init__(self, matrix) -> None:
            self.matrix = matrix

      def z(self, i):
            row = 2
            col = 2
            for _ in range(i-1,0,-1):
                col -= 1
                if (col < 0):
                    row -= 1
                    col = 2
            return self.matrix[row][col]


def _WGHT(matrix: _3x3WindowMatrix):
     # aspect gradients calculation
      wght1 = ((matrix.z(7) != None if 1 else 0) + 
            2*(matrix.z(4) != None if 1 else 0) + 
            (matrix.z(1) != None if 1 else 0))

      wght2 = ((matrix.z(9) != None if 1 else 0) + 
            2*(matrix.z(6) != None if 1 else 0) + 
            (matrix.z(3) != None if 1 else 0))

      wght3 = ((matrix.z(3) != None if 1 else 0) + 
            2*(matrix.z(2) != None if 1 else 0) + 
            (matrix.z(1) != None if 1 else 0))

      wght4 = ((matrix.z(9) != None if 1 else 0) + 
            2*(matrix.z(8) != None if 1 else 0) + 
            (matrix.z(7) != None if 1 else 0))


      fx = ((matrix.z(7) + 2*matrix.z(4) + matrix.z(1)) * 4 / wght1
      - (matrix.z(9) + 2*matrix.z(6) + matrix.z(3)) * 4 / wght2)

      fy = ((matrix.z(3) + 2*matrix.z(2) + matrix.z(1)) * 4 / wght3
      - (matrix.z(9) + 2*matrix.z(8) + matrix.z(7)) * 4 / wght4)

      return (fx, fy)


def _2FD(matrix: _3x3WindowMatrix, g):
      fx = (matrix.z(6) - matrix.z(4)) / (2*g)
      fy = (matrix.z(8) - matrix.z(2)) / (2*g)
      
      return (fx, fy)

def _3FDWRD(matrix: _3x3WindowMatrix, g):
      fx = (matrix.z(3) - matrix.z(1) + math.sqrt(2) * (matrix.z(6) - matrix.z(4)) + matrix.z(9) - matrix.z(7))/((4+2*math.sqrt(2))*g)
      fy = (matrix.z(7) - matrix.z(1) + math.sqrt(2) * (matrix.z(8) - matrix.z(2)) + matrix.z(9) - matrix.z(3))/((4+2*math.sqrt(2))*g)

      return (fx, fy)

def _3FD(matrix: _3x3WindowMatrix, g):
     fx = (matrix.z(3) - matrix.z(1) + matrix.z(6) - matrix.z(4) + matrix.z(9) - matrix.z(7)) / (6*g)
     fy = (matrix.z(7) - matrix.z(1) + matrix.z(8) - matrix.z(2) + matrix.z(9) - matrix.z(3)) / (6*g)

     return (fx, fy)

def _3FDWRSD(matrix: _3x3WindowMatrix, g):
     fx = (matrix.z(3) - matrix.z(1) + 2*(matrix.z(6) - matrix.z(4)) + matrix.z(9) - matrix.z(7)) / (8*g)
     fy = (matrix.z(7) - matrix.z(1) + 2*(matrix.z(8) - matrix.z(2)) + matrix.z(9) - matrix.z(3)) / (8*g)
     # Horn
     return (fx, fy)

def _FFD(matrix: _3x3WindowMatrix, g):
     fx = (matrix.z(3) - matrix.z(1) + matrix.z(9) - matrix.z(7)) / (4*g)
     fy = (matrix.z(7) - matrix.z(1) + matrix.z(9) - matrix.z(3)) / (4*g)

     return (fx, fy)

def _SimpleD(matrix: _3x3WindowMatrix, g):
     fx = (matrix.z(5) - matrix.z(4)) / g
     fy = (matrix.z(5) - matrix.z(2)) / g

     return (fx, fy)


functionList = (_2FD, _3FDWRD, _3FD, _3FDWRSD, _FFD, _SimpleD, _WGHT)