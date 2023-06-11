import sys 
from PyQt5.QtWidgets import *

app = QApplication(sys.argv)
label = QLabel("Hello PyQt")
label.show()
app.exec_()
print("1")
# import sys 
# from PyQt5.QtWidgets import *

# class MyWindow(QMainWindow):
#     def __init__(self):
#         super().__init__()


# app = QApplication(sys.argv)
# window = MyWindow()
# window.show()
# app.exec_()

import sys 
from PyQt5.QtWidgets import *
from PyQt5.QAxContainer import *

print("2")
class MyWindow(QMainWindow):
    print("3")
    def __init__(self):
        super().__init__()
        print("4")
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        print("5")
        self.ocx.dynamicCall("CommConnect()")
        print("6")
        self.ocx.OnEventConnect.connect(self.OnEventConnect)

    def OnEventConnect(self, err_code):
        print(err_code)

print("7")
app = QApplication(sys.argv)
print("8")
window = MyWindow()
print("9")
window.show()
print("10")
app.exec_()
print("11")

# set CONDA_FORCE_32BIT=1 
# conda create -n base python=3.8.5
