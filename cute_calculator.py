import tkinter as tk
from tkinter import messagebox
import random
import time

class CuteCalculator:
    def __init__(self, master):
        self.master = master
        master.title("귀여운 계산기")
        master.geometry("400x550")
        master.configure(bg="pink")

        self.problem_count = 0
        self.current_problem = 0
        self.correct_answers = 0
        self.operation = '+'
        self.start_time = 0
        self.total_time = 0

        self.create_widgets()

    def create_widgets(self):
        #   제목 프레임
        title_frame = tk.Frame(self.master, bg="pink")
        title_frame.pack(pady=(10, 5))

        # 게임 제목
        self.title_label = tk.Label(title_frame, text="Jenny's Counting Game", 
                                     font=("Arial", 18, "bold"), bg="pink", fg="black")
        self.title_label.pack(side=tk.TOP)

        # 부제목 추가 (제목 바로 오른쪽 아래에 위치)
        self.subtitle_label = tk.Label(title_frame, text="- 콰니 -", 
                                       font=("Arial", 12), bg="pink", fg="black")
        self.subtitle_label.pack(side=tk.LEFT, padx=(300, 0), pady=(5, 0))  # 오른쪽 여백 추가

        # 문제 세팅 프레임
        self.setting_frame = tk.Frame(self.master, bg="lightpink", bd=5, relief=tk.RAISED)
        self.setting_frame.pack(pady=5, padx=15, fill=tk.X)

        # 문제 수 선택
        tk.Label(self.setting_frame, text="문제 수를 선택하세요:", bg="lightpink").pack(pady=5)
        self.problem_count_var = tk.StringVar()
        self.problem_count_var.set("")
        self.problem_count_entry = tk.Entry(self.setting_frame, textvariable=self.problem_count_var, state='readonly', width=5)
        self.problem_count_entry.pack(pady=5)

        # 숫자 버튼과 사칙연산 버튼 프레임
        number_frame = tk.Frame(self.setting_frame, bg="lightpink")
        number_frame.pack(pady=5)

        # 사칙연산 버튼 (왼쪽에 세로로 배열)
        operations = ['+', '-', '*', '/']
        self.operation_buttons = {}
        for i, op in enumerate(operations):
            btn = tk.Button(number_frame, text=op, command=lambda x=op: self.set_operation(x), width=3)
            btn.grid(row=i, column=0, padx=(0, 10), pady=2)
            self.operation_buttons[op] = btn

        # 숫자 버튼 (3x4 그리드)
        for i in range(1, 10):
            tk.Button(number_frame, text=str(i), command=lambda x=i: self.add_number(x), width=5).grid(row=(i-1)//3, column=(i-1)%3 + 1, padx=2, pady=2)
        tk.Button(number_frame, text="0", command=lambda: self.add_number(0), width=5).grid(row=3, column=2, padx=2, pady=2)
        tk.Button(number_frame, text="Clear", command=self.clear_number, width=5).grid(row=3, column=1, padx=2, pady=2)
        tk.Button(number_frame, text="확인", command=self.start_quiz, width=5).grid(row=3, column=3, padx=2, pady=2)

        # 선택된 연산 표시 (기본값은 +)
        self.set_operation('+')

        # 구분선
        tk.Frame(self.master, bg="purple", height=1).pack(fill=tk.X, padx=10, pady=(2, 0))

        # 문제 표시
        self.problem_label = tk.Label(self.master, text="", font=("Arial", 22), bg="white" , width=10)
        self.problem_label.pack(pady=(5, 5), padx=10)

        # 답 입력
        self.answer_var = tk.StringVar()
        self.answer_var.set("")
        self.answer_entry = tk.Entry(self.master, textvariable=self.answer_var, state='readonly', width=5, font=("Arial", 18), justify='center')
        self.answer_entry.pack(pady=(0, 2))

        # 숫자 버튼 (답 입력용)
        answer_frame = tk.Frame(self.master, bg="hotpink")
        answer_frame.pack(pady=10)
        for i in range(1, 10):
            tk.Button(answer_frame, text=str(i), command=lambda x=i: self.add_answer(x), width=5).grid(row=(i-1)//3, column=(i-1)%3, padx=5, pady=5)
        tk.Button(answer_frame, text="0", command=lambda: self.add_answer(0), width=5).grid(row=3, column=1, padx=5, pady=5)
        tk.Button(answer_frame, text="Clear", command=self.clear_answer, width=5).grid(row=3, column=0, padx=5, pady=5)
        tk.Button(answer_frame, text="제출", command=self.check_answer, width=5).grid(row=3, column=2, padx=5, pady=5)

    def add_number(self, number):
        current = self.problem_count_var.get()
        if len(current) < 2:
            self.problem_count_var.set(current + str(number))

    def clear_number(self):
        self.problem_count_var.set("")

    def start_quiz(self):
        try:
            self.problem_count = int(self.problem_count_var.get())
            if self.problem_count > 0:
                self.current_problem = 0
                self.correct_answers = 0
                self.total_time = 0
                self.next_problem()
            else:
                messagebox.showwarning("경고", "1개 이상의 문제 수를 선택해주세요.")
        except ValueError:
            messagebox.showwarning("경고", "올바른 문제 수를 선택해주세요.")
            
    def set_operation(self, op):
        # 이전 버튼 색상 초기화
        for button in self.operation_buttons.values():
            button.config(bg='lightgray')
        
        # 현재 선택된 연산 색상 변경
        self.operation = op
        self.operation_buttons[op].config(bg='darkgray')

    def next_problem(self):
        if self.current_problem < self.problem_count:
            self.current_problem += 1
            x = random.randint(0, 100)
            y = random.randint(0, 10)
            self.problem_label.config(text=f"{x} {self.operation} {y} = ?")
            self.answer_var.set("")
            self.correct_answer = eval(f"{x} {self.operation} {y}")
            self.start_time = time.time()
        else:
            avg_time = self.total_time / self.problem_count if self.problem_count > 0 else 0
            messagebox.showinfo("퀴즈 종료", 
                                f"퀴즈가 끝났습니다!\n"
                                f"{self.problem_count}문제 중 {self.correct_answers}개 맞췄습니다.\n"
                                f"총 소요 시간: {self.total_time:.2f}초\n"
                                f"문제당 평균 시간: {avg_time:.2f}초")

    def add_answer(self, number):
        current = self.answer_var.get()
        if len(current) < 3:
            self.answer_var.set(current + str(number))

    def clear_answer(self):
        self.answer_var.set("")

    def check_answer(self):
        end_time = time.time()
        elapsed_time = end_time - self.start_time
        self.total_time += elapsed_time
        
        try:
            user_answer = float(self.answer_var.get())
            if abs(user_answer - self.correct_answer) < 0.01:  # 부동소수점 오차를 고려
                self.correct_answers += 1
                messagebox.showinfo("정답", f"맞았습니다!\n소요 시간: {elapsed_time:.2f}초")
            else:
                messagebox.showinfo("오답", f"틀렸습니다. 정답은 {self.correct_answer:.2f}입니다.\n소요 시간: {elapsed_time:.2f}초")
            self.next_problem()
        except ValueError:
            messagebox.showwarning("경고", "올바른 답을 입력해주세요.")

root = tk.Tk()
calculator = CuteCalculator(root)
root.mainloop()