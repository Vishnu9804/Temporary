// Quiz Data - 10 Simple Questions
var questions = [
    { question: "What does HTML stand for?", options: ["Hyper Text Preprocessor", "Hyper Text Markup Language", "Hyper Text Multiple Language", "Hyper Tool Multi Language"], answer: 1 },
    { question: "Which language runs in a web browser?", options: ["Java", "C", "Python", "JavaScript"], answer: 3 },
    { question: "What does CSS stand for?", options: ["Central Style Sheets", "Cascading Style Sheets", "Cascading Simple Sheets", "Cars SUVs Sailboats"], answer: 1 },
    { question: "What year was JavaScript launched?", options: ["1996", "1995", "1994", "None of the above"], answer: 1 },
    { question: "Which HTML tag is used to define an internal style sheet?", options: ["<script>", "<style>", "<css>", "<link>"], answer: 1 },
    { question: "Which is not a JavaScript data type?", options: ["Number", "Boolean", "Float", "String"], answer: 2 },
    { question: "How do you write 'Hello World' in an alert box?", options: ["msg('Hello World');", "alertBox('Hello World');", "alert('Hello World');", "msgBox('Hello World');"], answer: 2 },
    { question: "Which symbol is used for comments in JavaScript?", options: ["//", "", "/* */", "#"], answer: 0 },
    { question: "What is the correct way to write a JavaScript array?", options: ["var colors = 1 = ('red'), 2 = ('green')", "var colors = (1:'red', 2:'green')", "var colors = ['red', 'green', 'blue']", "var colors = 'red', 'green', 'blue'"], answer: 2 },
    { question: "Which event occurs when the user clicks on an HTML element?", options: ["onmouseover", "onchange", "onclick", "onmouseclick"], answer: 2 }
];

// State Variables (using var as requested to avoid ES6)
var currentQuestionIndex = 0;
var score = 0;
var timer;
var timeLeft = 60;
var userAnswers = []; // To store user choices for review

// DOM Elements
var startScreen = document.getElementById('start-screen');
var quizScreen = document.getElementById('quiz-screen');
var resultScreen = document.getElementById('result-screen');
var questionText = document.getElementById('question-text');
var optionsContainer = document.getElementById('options-container');
var timeDisplay = document.getElementById('time');
var finalScoreDisplay = document.getElementById('final-score');
var reviewContainer = document.getElementById('review-container');

function startQuiz() {
    startScreen.classList.add('hidden');
    quizScreen.classList.remove('hidden');
    currentQuestionIndex = 0;
    score = 0;
    timeLeft = 60;
    userAnswers = [];
    
    // Start Timer
    timer = setInterval(function() {
        timeLeft--;
        timeDisplay.textContent = timeLeft;
        if (timeLeft <= 0) {
            endQuiz();
        }
    }, 1000);

    loadQuestion();
}

function loadQuestion() {
    // Clear previous options
    optionsContainer.innerHTML = '';
    
    var currentQuestion = questions[currentQuestionIndex];
    questionText.textContent = (currentQuestionIndex + 1) + ". " + currentQuestion.question;

    // Create buttons for options
    for (var i = 0; i < currentQuestion.options.length; i++) {
        var btn = document.createElement('button');
        btn.textContent = currentQuestion.options[i];
        btn.className = 'option-btn';
        
        btn.setAttribute('data-index', i);
        btn.onclick = function(e) {
            selectAnswer(parseInt(e.target.getAttribute('data-index')));
        };
        optionsContainer.appendChild(btn);
    }
}

function selectAnswer(selectedIndex) {
    var correctIndex = questions[currentQuestionIndex].answer;
    
    // Save result for review
    userAnswers.push({
        question: questions[currentQuestionIndex].question,
        selected: selectedIndex,
        correct: correctIndex,
        options: questions[currentQuestionIndex].options
    });

    if (selectedIndex === correctIndex) {
        score++;
    }

    currentQuestionIndex++;

    if (currentQuestionIndex < questions.length) {
        loadQuestion();
    } else {
        endQuiz();
    }
}

function endQuiz() {
    clearInterval(timer);
    quizScreen.classList.add('hidden');
    resultScreen.classList.remove('hidden');
    finalScoreDisplay.textContent = score;
    renderReview();
}

function renderReview() {
    reviewContainer.innerHTML = '';
    
    for (var i = 0; i < userAnswers.length; i++) {
        var item = userAnswers[i];
        var div = document.createElement('div');
        div.className = 'review-item';
        
        var status = (item.selected === item.correct) ? 
            '<span class="review-correct">Correct</span>' : 
            '<span class="review-wrong">Wrong</span>';

        // Intern-style simple concatenation
        var html = '<p><strong>Q' + (i + 1) + ': ' + item.question + '</strong></p>';
        html += '<p>Your Answer: ' + item.options[item.selected] + ' (' + status + ')</p>';
        if (item.selected !== item.correct) {
            html += '<p class="review-correct">Correct Answer: ' + item.options[item.correct] + '</p>';
        }
        
        div.innerHTML = html;
        reviewContainer.appendChild(div);
    }
}

function restartQuiz() {
    resultScreen.classList.add('hidden');
    startScreen.classList.remove('hidden');
}