"""Intent classification component using TF-IDF + Logistic Regression."""

from typing import Any, NamedTuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

SUPPORTED_INTENTS: list[str] = [
    "CALCULATOR",
    "CRYPTO",
    "DOCUMENT",
    "GENERAL",
    "MEMORY",
    "REMINDER",
    "WEATHER",
    "WEB_SEARCH",
]

# Curated, self-contained training dataset covering all 8 intents
DEFAULT_TRAINING_DATA: list[tuple[str, str]] = [
    # GENERAL
    ("hello how are you doing today", "GENERAL"),
    ("hi there good morning assistant", "GENERAL"),
    ("who are you and what are your capabilities", "GENERAL"),
    ("nice to meet you ai companion", "GENERAL"),
    ("thanks for your assistance goodbye", "GENERAL"),
    ("tell me a funny joke to make me laugh", "GENERAL"),
    ("can we chat for a little while", "GENERAL"),
    ("good evening hope your day was pleasant", "GENERAL"),
    ("what is your name and origin", "GENERAL"),
    ("hey contextai give me a hand please", "GENERAL"),
    ("how is everything going with you", "GENERAL"),
    ("thank you kindly have a wonderful afternoon", "GENERAL"),

    # WEATHER
    ("what is the weather condition in New York", "WEATHER"),
    ("is it going to rain or pour tomorrow", "WEATHER"),
    ("what is the current outdoor temperature outside", "WEATHER"),
    ("will it snow in Denver this winter weekend", "WEATHER"),
    ("show me the seven day weather forecast", "WEATHER"),
    ("do I need an umbrella for rain storms today", "WEATHER"),
    ("is it sunny cloudy or overcast right now", "WEATHER"),
    ("check the atmospheric humidity and wind speed", "WEATHER"),
    ("what is the weather forecast for today", "WEATHER"),
    ("is it hot humid or freezing cold outside", "WEATHER"),
    ("how cold is the climate going to be tonight", "WEATHER"),
    ("give me the local temperature and meteorological report", "WEATHER"),

    # CRYPTO
    ("what is the current price of Bitcoin", "CRYPTO"),
    ("how much is Ethereum crypto trading for right now", "CRYPTO"),
    ("show me crypto market prices and top gainers", "CRYPTO"),
    ("is Solana crypto coin rising today", "CRYPTO"),
    ("check the current crypto BTC price and exchange rate", "CRYPTO"),
    ("what is the market cap of Dogecoin crypto", "CRYPTO"),
    ("track cryptocurrency prices and tokens for me", "CRYPTO"),
    ("how is the crypto blockchain market doing this week", "CRYPTO"),
    ("buy or sell Bitcoin cryptocurrency tokens", "CRYPTO"),
    ("what is the Ethereum cryptocurrency token valuation today", "CRYPTO"),
    ("give me the latest cryptocurrency exchange rates", "CRYPTO"),
    ("how is Bitcoin BTC performing on the crypto exchange", "CRYPTO"),

    # WEB_SEARCH
    ("search the web for latest technology breakthroughs", "WEB_SEARCH"),
    ("look up web updates on the space mission launch", "WEB_SEARCH"),
    ("search online for the best dining restaurants nearby", "WEB_SEARCH"),
    ("find internet articles online about quantum computing research", "WEB_SEARCH"),
    ("search google online for the latest sports scores", "WEB_SEARCH"),
    ("search the web for recent medical research discoveries", "WEB_SEARCH"),
    ("look up who won the championship game online", "WEB_SEARCH"),
    ("browse the internet to find news on current stock trends", "WEB_SEARCH"),
    ("search the internet for recent global headlines and news", "WEB_SEARCH"),
    ("look up online articles about artificial intelligence trends", "WEB_SEARCH"),
    ("find information on the internet about clean renewable energy", "WEB_SEARCH"),
    ("search the web to find movie reviews and ratings", "WEB_SEARCH"),

    # CALCULATOR
    ("calculate 15 percent tip of 240 dollars", "CALCULATOR"),
    ("what is 45 multiplied by 12", "CALCULATOR"),
    ("solve this math algebra equation 3x + 15 = 45", "CALCULATOR"),
    ("what is the square root of 144 in mathematics", "CALCULATOR"),
    ("compute 250 divided by 5", "CALCULATOR"),
    ("calculate the math sum total of 89 45 and 12", "CALCULATOR"),
    ("what is 2 to the power exponent of 8", "CALCULATOR"),
    ("evaluate math expression 100 minus 37.5", "CALCULATOR"),
    ("calculate arithmetic result for 50 divided by 2", "CALCULATOR"),
    ("multiply 7 times 8 on calculator", "CALCULATOR"),
    ("what is 99 plus 142 minus 33", "CALCULATOR"),
    ("calculate the numerical average of 10 20 and 30", "CALCULATOR"),

    # MEMORY
    ("remember that my favorite color is navy blue", "MEMORY"),
    ("what did I tell you about my dietary preferences in memory", "MEMORY"),
    ("save this memory note my sister birthday is on June 12th", "MEMORY"),
    ("do you remember what my dog name is from past conversations", "MEMORY"),
    ("recall the notes I saved yesterday about project milestones", "MEMORY"),
    ("store this memory detail that I work as an engineer", "MEMORY"),
    ("what do you know from memory about my personal preferences", "MEMORY"),
    ("please remember in memory that I prefer espresso over tea", "MEMORY"),
    ("recall my favorite food from saved personal memory", "MEMORY"),
    ("store this profile information in my persistent memory", "MEMORY"),
    ("what memories do you have saved about my background", "MEMORY"),
    ("remember that I live in San Francisco California", "MEMORY"),

    # DOCUMENT
    ("summarize the uploaded PDF document file", "DOCUMENT"),
    ("extract the key points from the attached contract document", "DOCUMENT"),
    ("read through this research paper document and highlight conclusions", "DOCUMENT"),
    ("what does section 3 of the report document say", "DOCUMENT"),
    ("review the legal document for clauses regarding liability", "DOCUMENT"),
    ("can you review the text in this uploaded doc document", "DOCUMENT"),
    ("analyze the attached invoice document and find the total balance", "DOCUMENT"),
    ("find all mentions of budget allocation in the document report", "DOCUMENT"),
    ("summarize the file document content and key findings", "DOCUMENT"),
    ("read the attached PDF document and tell me what it is about", "DOCUMENT"),
    ("extract tables and paragraphs from this uploaded document", "DOCUMENT"),
    ("explain the main theme of this doc file document", "DOCUMENT"),

    # REMINDER
    ("remind me to drink a glass of water in 30 minutes", "REMINDER"),
    ("set a reminder for my dentist appointment on Thursday at 2 PM", "REMINDER"),
    ("schedule an alert reminder to submit my assignment tonight", "REMINDER"),
    ("remind me to call mom at 6 PM tomorrow evening", "REMINDER"),
    ("create a reminder for the team standup meeting at 9 AM", "REMINDER"),
    ("notify me and remind me when it is time to take my medicine", "REMINDER"),
    ("set a timer and reminder to check the oven in 20 minutes", "REMINDER"),
    ("add a reminder alert to pay the utility electric bill by Friday", "REMINDER"),
    ("remind me about the project deadline tomorrow morning", "REMINDER"),
    ("set an alarm reminder to wake up early tomorrow morning", "REMINDER"),
    ("create a calendar reminder to attend the lecture at 3 PM", "REMINDER"),
    ("remind me to buy groceries this evening after work", "REMINDER"),
]


def get_default_training_data() -> tuple[list[str], list[str]]:
    """Return default training dataset as separated lists of texts and labels."""
    texts = [item[0] for item in DEFAULT_TRAINING_DATA]
    labels = [item[1] for item in DEFAULT_TRAINING_DATA]
    return texts, labels


class PredictionResult(NamedTuple):
    """Container for intent prediction output and confidence."""

    intent: str
    confidence: float


class IntentClassifier:
    """TF-IDF + Logistic Regression intent classifier."""

    def __init__(
        self,
        c_param: float = 5.0,
        max_iter: int = 1000,
        random_state: int = 42,
    ) -> None:
        self.c_param = c_param
        self.max_iter = max_iter
        self.random_state = random_state

        self.vectorizer: TfidfVectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            lowercase=True,
            sublinear_tf=True,
        )
        self.classifier: LogisticRegression = LogisticRegression(
            C=self.c_param,
            max_iter=self.max_iter,
            random_state=self.random_state,
        )
        self.is_trained: bool = False

    def train(
        self,
        texts: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> None:
        """Train the TF-IDF vectorizer and Logistic Regression classifier."""
        if texts is None or labels is None:
            texts, labels = get_default_training_data()

        if len(texts) != len(labels):
            raise ValueError("Number of texts must match number of labels.")

        if not texts:
            raise ValueError("Training dataset cannot be empty.")

        x_vec = self.vectorizer.fit_transform(texts)
        self.classifier.fit(x_vec, labels)
        self.is_trained = True

    def predict(self, text: str) -> PredictionResult:
        """Predict the intent and return intent label with confidence probability."""
        if not self.is_trained:
            # Auto-train with default dataset if not yet explicitly trained
            self.train()

        x_vec = self.vectorizer.transform([text])
        predicted_label = self.classifier.predict(x_vec)[0]
        probabilities = self.classifier.predict_proba(x_vec)[0]
        confidence = float(max(probabilities))

        return PredictionResult(intent=str(predicted_label), confidence=confidence)

    def evaluate(
        self,
        texts: list[str] | None = None,
        labels: list[str] | None = None,
        test_size: float = 0.25,
        random_state: int = 42,
    ) -> dict[str, Any]:
        """Evaluate classifier using held-out split and compute standard metrics."""
        if texts is None or labels is None:
            texts, labels = get_default_training_data()

        x_train, x_test, y_train, y_test = train_test_split(
            texts,
            labels,
            test_size=test_size,
            random_state=random_state,
            stratify=labels,
        )

        eval_vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            lowercase=True,
            sublinear_tf=True,
        )
        eval_classifier = LogisticRegression(
            C=self.c_param,
            max_iter=self.max_iter,
            random_state=self.random_state,
        )

        x_train_vec = eval_vectorizer.fit_transform(x_train)
        eval_classifier.fit(x_train_vec, y_train)

        x_test_vec = eval_vectorizer.transform(x_test)
        y_pred = eval_classifier.predict(x_test_vec)

        class_labels = sorted(list(set(labels)))
        cm = confusion_matrix(y_test, y_pred, labels=class_labels)

        return {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred, average="weighted", zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, average="weighted", zero_division=0)),
            "f1_score": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
            "confusion_matrix": cm.tolist(),
            "labels": class_labels,
            "test_sample_count": len(y_test),
        }
