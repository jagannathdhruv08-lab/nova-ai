# ==========================================
# NOVA MINI-QUIZ FEATURE
# ==========================================
# Fun knowledge quizzes for breaks between study/work
# Multiple categories, automatic scoring


# Quiz questions by category
QUIZ_QUESTIONS = {
    "science": [
        {
            "question": "What is the powerhouse of the cell?",
            "options": ["Mitochondria", "Nucleus", "Ribosome", "Golgi apparatus"],
            "answer": "Mitochondria",
            "explanation": "Mitochondria generate energy (ATP) for the cell."
        },
        {
            "question": "H2O is the chemical formula for?",
            "options": ["Water", "Carbon dioxide", "Oxygen", "Hydrochloric acid"],
            "answer": "Water",
            "explanation": "H2O represents one water molecule."
        }
    ],
    "general": [
        {
            "question": "Who wrote 'Romeo and Juliet'?",
            "options": ["Charles Dickens", "William Shakespeare", "Mark Twain", "Jane Austen"],
            "answer": "William Shakespeare",
            "explanation": "William Shakespeare wrote this famous tragedy."
        },
        {
            "question": "Which planet is known as the Red Planet?",
            "options": ["Venus", "Mars", "Jupiter", "Saturn"],
            "answer": "Mars",
            "explanation": "Mars appears red due to iron oxide on its surface."
        }
    ],
    "math": [
        {
            "question": "What is 15 + 7?",
            "options": ["22", "23", "24", "21"],
            "answer": "22",
            "explanation": "15 + 7 = 22"
        },
        {
            "question": "What is the square root of 64?",
            "options": ["6", "7", "8", "9"],
            "answer": "8",
            "explanation": "8 × 8 = 64"
        }
    ]
}


def start_quiz(category="general"):
    """Start a quiz in the specified category.
    
    Args:
        category: Quiz category ("science", "general", "math")
    Returns quiz setup dict.
    """
    try:
        questions = QUIZ_QUESTIONS.get(category, QUIZ_QUESTIONS["general"])
        return {
            "success": True,
            "feature": "mini_quizzes",
            "category": category,
            "total_questions": len(questions),
            "questions": questions,
            "current_question": 0,
            "score": 0,
            "message": f"Started {category} quiz with {len(questions)} questions"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Quiz start failed: {str(e)}",
            "feature": "mini_quizzes",
            "error": str(e)
        }


def check_answer(category, question_index, selected_answer):
    """Check if the selected answer is correct.
    
    Args:
        category: Quiz category
        question_index: Which question (0-based)
        selected_answer: The chosen option
    Returns dict with correctness and explanation.
    """
    try:
        questions = QUIZ_QUESTIONS.get(category, QUIZ_QUESTIONS["general"])
        
        if question_index < 0 or question_index >= len(questions):
            return {
                "success": False,
                "message": "Invalid question number",
                "feature": "mini_quizzes",
                "error": "Question index out of range"
            }
        
        question = questions[question_index]
        is_correct = selected_answer.strip().lower() == question["answer"].strip().lower()
        
        return {
            "success": True,
            "feature": "mini_quizzes",
            "question": question["question"],
            "selected_answer": selected_answer,
            "correct_answer": question["answer"],
            "is_correct": is_correct,
            "explanation": question["explanation"],
            "new_score": question_index + 1 if is_correct else question_index,
            "message": "Correct! 👍" if is_correct else f"Wrong! The correct answer was: {question['answer']}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Answer check failed: {str(e)}",
            "feature": "mini_quizzes",
            "error": str(e)
        }


def get_quiz_category_options():
    """Get available quiz categories."""
    try:
        categories = list(QUIZ_QUESTIONS.keys())
        return {
            "success": True,
            "feature": "mini_quizzes",
            "categories": categories,
            "message": f"Available categories: {', '.join(categories)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Could not get categories: {str(e)}",
            "feature": "mini_quizzes",
            "error": str(e)
        }


# Feature metadata
__version__ = "1.0.0"
__all__ = ["start_quiz", "check_answer", "get_quiz_category_options"]