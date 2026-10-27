"""Intent classification component using TF-IDF + Logistic Regression.

Training needs scikit-learn (a development dependency). The server instead loads the trained weights from
intent_model.json (python -m scripts.export_intent_model) and predicts with numpy, which keeps
scikit-learn and SciPy, about 120 MB, out of a 512 MB instance. The two give identical predictions
(tests/test_classifier.py checks this).
"""

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

MODEL_FILE = Path(__file__).with_name("intent_model.json")
_TOKEN = re.compile(r"(?u)\b\w\w+\b")  # scikit-learn's default token_pattern

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
        self.params: dict[str, Any] | None = None  # trained weights, see export()
        self.is_trained: bool = False

    def _models(self) -> tuple[Any, Any]:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", lowercase=True, sublinear_tf=True)
        classifier = LogisticRegression(C=self.c_param, max_iter=self.max_iter, random_state=self.random_state)
        return vectorizer, classifier

    def train(
        self,
        texts: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> None:
        """Train the TF-IDF vectorizer and Logistic Regression classifier (needs scikit-learn)."""
        if texts is None or labels is None:
            texts, labels = get_default_training_data()

        if len(texts) != len(labels):
            raise ValueError("Number of texts must match number of labels.")

        if not texts:
            raise ValueError("Training dataset cannot be empty.")

        vectorizer, classifier = self._models()
        classifier.fit(vectorizer.fit_transform(texts), labels)
        vocabulary = sorted(vectorizer.vocabulary_, key=vectorizer.vocabulary_.get)
        self.params = {
            "vocabulary": vocabulary,
            "idf": vectorizer.idf_.tolist(),
            "stop_words": sorted(vectorizer.get_stop_words()),
            "coef": classifier.coef_.tolist(),
            "intercept": classifier.intercept_.tolist(),
            "classes": [str(c) for c in classifier.classes_],
        }
        self._prepare()
        self.is_trained = True

    def export(self, path: Path = MODEL_FILE) -> None:
        """Write the trained weights for the server to load without scikit-learn."""
        if self.params is None:
            raise ValueError("Train the classifier before exporting it.")
        path.write_text(json.dumps(self.params, separators=(",", ":")) + "\n")

    @classmethod
    def load(cls, path: Path = MODEL_FILE) -> "IntentClassifier":
        classifier = cls()
        classifier.params = json.loads(path.read_text())
        classifier._prepare()
        classifier.is_trained = True
        return classifier

    def _prepare(self) -> None:
        p = self.params or {}
        self._index = {term: i for i, term in enumerate(p["vocabulary"])}
        self._stop = frozenset(p["stop_words"])
        self._idf = np.array(p["idf"])
        self._coef = np.array(p["coef"])
        self._intercept = np.array(p["intercept"])

    def _vector(self, text: str) -> np.ndarray:
        """scikit-learn's TfidfVectorizer.transform: stop words removed, then 1-2 grams, sublinear tf, l2."""
        tokens = [t for t in _TOKEN.findall(text.lower()) if t not in self._stop]
        grams = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        x = np.zeros(len(self._index))
        for gram, count in Counter(grams).items():
            if (i := self._index.get(gram)) is not None:
                x[i] = 1 + math.log(count)
        x *= self._idf
        norm = np.linalg.norm(x)
        return x / norm if norm else x

    def predict(self, text: str) -> PredictionResult:
        """Predict the intent and return intent label with confidence probability."""
        if not self.is_trained:
            if MODEL_FILE.exists():
                loaded = self.load()
                self.params, self.is_trained = loaded.params, True
                self._prepare()
            else:
                self.train()

        scores = self._coef @ self._vector(text) + self._intercept
        if len(scores) == 1:  # two classes: one logistic score for the second class
            p = 1 / (1 + math.exp(-scores[0]))
            probabilities = np.array([1 - p, p])
        else:
            exp = np.exp(scores - scores.max())
            probabilities = exp / exp.sum()
        best = int(np.argmax(probabilities))
        return PredictionResult(intent=self.params["classes"][best], confidence=float(probabilities[best]))

    def evaluate(
        self,
        texts: list[str] | None = None,
        labels: list[str] | None = None,
        test_size: float = 0.25,
        random_state: int = 42,
    ) -> dict[str, Any]:
        """Evaluate classifier using held-out split and compute standard metrics (needs scikit-learn)."""
        from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
        from sklearn.model_selection import train_test_split

        if texts is None or labels is None:
            texts, labels = get_default_training_data()

        x_train, x_test, y_train, y_test = train_test_split(
            texts,
            labels,
            test_size=test_size,
            random_state=random_state,
            stratify=labels,
        )

        eval_vectorizer, eval_classifier = self._models()

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
