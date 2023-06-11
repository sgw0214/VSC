    
# set CONDA_FORCE_32BIT=1 
# conda create -n base python=3.8.5

from pykiwoom.kiwoom import *

kiwoom = Kiwoom()
kiwoom.CommConnect(block=True)
print("블록킹 로그인 완료")