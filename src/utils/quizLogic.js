export const calculateScore = (userAnswers) => {
    return userAnswers.reduce((score, answer) => {
        return score + (answer.selected === answer.correct ? 1 : 0);
    }, 0);
};

export const isCorrect = (selected, correct) => selected === correct;

export const isQuizOver = (currentIndex, totalQuestions) => {
    return currentIndex >= totalQuestions;
};