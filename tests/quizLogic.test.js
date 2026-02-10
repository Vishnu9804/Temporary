import { calculateScore, isCorrect, isQuizOver } from '../src/utils/quizLogic';

describe('Quiz Logic Utilities', () => {
    
    test('calculateScore should correctly sum correct answers', () => {
        const mockAnswers = [
            { selected: 1, correct: 1 }, 
            { selected: 0, correct: 1 }, 
            { selected: 2, correct: 2 }  
        ];
        expect(calculateScore(mockAnswers)).toBe(2);
    });

    test('calculateScore should return 0 for empty answers', () => {
        expect(calculateScore([])).toBe(0);
    });

    // Test 2: Check Correctness
    test('isCorrect should return true for matching values', () => {
        expect(isCorrect(1, 1)).toBe(true);
    });

    test('isCorrect should return false for non-matching values', () => {
        expect(isCorrect(0, 1)).toBe(false);
    });

    // Test 3: Quiz Status
    test('isQuizOver should return true when index >= total', () => {
        expect(isQuizOver(10, 10)).toBe(true);
    });

    test('isQuizOver should return false when index < total', () => {
        expect(isQuizOver(5, 10)).toBe(false);
    });
});