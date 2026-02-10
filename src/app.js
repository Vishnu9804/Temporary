import { questions } from './data/questions.js';
import { calculateScore, isQuizOver } from './utils/quizLogic.js';

let state = {
    currentQuestionIndex: 0,
    timer: null,
    timeLeft: 60,
    userAnswers: [] 
};

const dom = {
    startScreen: document.getElementById('start-screen'),
    quizScreen: document.getElementById('quiz-screen'),
    resultScreen: document.getElementById('result-screen'),
    questionText: document.getElementById('question-text'),
    optionsContainer: document.getElementById('options-container'),
    timeDisplay: document.getElementById('time'),
    finalScoreDisplay: document.getElementById('final-score'),
    reviewContainer: document.getElementById('review-container'),
    paletteContainer: document.getElementById('question-palette'),
    btnStart: document.querySelector('#start-screen .btn'),
    btnNext: document.getElementById('next-btn'),
    btnPrev: document.getElementById('previous-btn'),
    btnExit: document.getElementById('exit-btn'),
    btnRestart: document.querySelector('#result-screen .btn')
};

const init = () => {
    dom.btnStart.addEventListener('click', startQuiz);
    dom.btnNext.addEventListener('click', nextQuestion);
    dom.btnPrev.addEventListener('click', previousQuestion);
    dom.btnExit.addEventListener('click', endQuiz);
    dom.btnRestart.addEventListener('click', restartQuiz);
};

const startQuiz = () => {
    dom.startScreen.classList.add('hidden');
    dom.quizScreen.classList.remove('hidden');
    dom.resultScreen.classList.add('hidden');

    state = {
        currentQuestionIndex: 0,
        timeLeft: 60,
        userAnswers: [],
        timer: setInterval(updateTimer, 1000)
    };
    
    loadQuestion();
};

const updateTimer = () => {
    state.timeLeft--;
    dom.timeDisplay.textContent = state.timeLeft;
    if (state.timeLeft <= 0) {
        endQuiz();
    }
};

const loadQuestion = () => {
    dom.optionsContainer.innerHTML = '';
    
    const currentQ = questions[state.currentQuestionIndex];
    dom.questionText.textContent = `${state.currentQuestionIndex + 1}. ${currentQ.question}`;

    const isFirst = state.currentQuestionIndex === 0;
    const isLast = state.currentQuestionIndex === questions.length - 1;
    
    dom.btnPrev.classList.toggle('hidden', isFirst);
    dom.btnNext.classList.toggle('hidden', isLast);
    dom.btnExit.classList.toggle('hidden', false);

    const existingAnswer = state.userAnswers.find(a => a.currentIndex === state.currentQuestionIndex);
    const selectedIdx = existingAnswer ? existingAnswer.selected : null;

    currentQ.options.forEach((opt, index) => {
        const btn = document.createElement('button');
        btn.textContent = opt;
        btn.className = `option-btn ${selectedIdx === index ? 'selected' : ''}`;
        
        btn.addEventListener('click', () => handleSelect(index));
        
        dom.optionsContainer.appendChild(btn);
    });

    updatePalette();
};

const handleSelect = (selectedIndex) => {
    const currentQ = questions[state.currentQuestionIndex];
    
    const existingIndex = state.userAnswers.findIndex(a => a.currentIndex === state.currentQuestionIndex);

    const answerObject = {
        currentIndex: state.currentQuestionIndex,
        question: currentQ.question,
        selected: selectedIndex,
        correct: currentQ.answer,
        options: currentQ.options
    };

    if (existingIndex > -1) {
        state.userAnswers[existingIndex] = answerObject;
    } else {
        state.userAnswers.push(answerObject);
    }

    if (state.currentQuestionIndex < questions.length - 1) {
    } else {
        endQuiz();
        return;
    }
    
    loadQuestion();
};

const nextQuestion = () => {
    if (!isQuizOver(state.currentQuestionIndex + 1, questions.length)) {
        state.currentQuestionIndex++;
        loadQuestion();
    }
};

const previousQuestion = () => {
    if (state.currentQuestionIndex > 0) {
        state.currentQuestionIndex--;
        loadQuestion();
    }
};

const endQuiz = () => {
    clearInterval(state.timer);
    dom.quizScreen.classList.add('hidden');
    dom.resultScreen.classList.remove('hidden');
    
    const finalScore = calculateScore(state.userAnswers);
    dom.finalScoreDisplay.textContent = finalScore;
    
    renderReview();
};

const renderReview = () => {
    dom.reviewContainer.innerHTML = '';
    
    const sortedAnswers = [...state.userAnswers].sort((a,b) => a.currentIndex - b.currentIndex);

    sortedAnswers.forEach((item, i) => {
        const isCorrect = item.selected === item.correct;
        const div = document.createElement('div');
        div.className = `review-item ${isCorrect ? 'correct' : 'wrong'}`;

        const myAnswer = item.options[item.selected];
        const rightAnswer = item.options[item.correct];

        div.innerHTML = `
            <strong>${item.currentIndex + 1}. ${item.question}</strong>
            <p>Your Answer: <span class="${isCorrect ? 'txt-green' : 'txt-red'}">${myAnswer}</span></p>
            ${!isCorrect ? `<p>Correct Answer: <span class="txt-green">${rightAnswer}</span></p>` : ''}
        `;
        dom.reviewContainer.appendChild(div);
    });
};

const updatePalette = () => {
    dom.paletteContainer.innerHTML = '';
    
    questions.forEach((_, index) => {
        const circle = document.createElement('div');
        circle.innerText = index + 1;
        circle.className = 'palette-item';

        const isAnswered = state.userAnswers.some(a => a.currentIndex === index);
        if (isAnswered) circle.classList.add('answered');
        if (index === state.currentQuestionIndex) circle.classList.add('active');

        dom.paletteContainer.appendChild(circle);
    });
};

const restartQuiz = () => {
    dom.resultScreen.classList.add('hidden');
    dom.startScreen.classList.remove('hidden');
};

document.addEventListener('DOMContentLoaded', init);