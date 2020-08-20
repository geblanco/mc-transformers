import tqdm
import logging

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import SnowballStemmer, WordNetLemmatizer

from typing import List, Callable
from transformers import PreTrainedTokenizer
from mc_transformers.data_classes import InputFeatures, InputExample


logger = logging.getLogger(__name__)


class TextTokenizer(object):
    stop_words = stopwords.words("english")
    lemmatizer = WordNetLemmatizer()
    stemmer = SnowballStemmer("english")

    def __call__(self, text):
        text_tokens = word_tokenize(text.lower().strip())
        return [
            self.stemmer.stem(self.lemmatizer.lemmatize(w))
            for w in text_tokens if w not in self.stop_words
        ]


def argmax(arr: List) -> int:
    return max(enumerate(arr), key=lambda elem: len(elem[1]))[0]


def should_correct_label(
    window_context: str,
    answer: str,
    no_answer_text: str,
    text_tokenizer: TextTokenizer,
) -> bool:
    # find if the answer is contained in the context,
    # which possibly indicates that the current window
    # context is enough to guess the answer
    ctx = window_context.lower()
    ans = answer.lower()
    correct = no_answer_text == ans or ctx.find(ans) != -1
    if not correct:
        ctx_tokens = text_tokenizer(ctx)
        ans_tokens = text_tokenizer(ans)
        nof_correct = sum([
            1 if token in ctx_tokens else 0
            for token in ans_tokens
        ])
        if nof_correct > 0:
            nof_correct /= len(ans_tokens)
        correct = nof_correct > 0.5

    return correct


def should_window(
    example: InputExample, tokenizer: PreTrainedTokenizer, max_length: int
) -> bool:
    # three special tokens will be added, remove them from the count
    max_length -= 3
    context = example.contexts[0]
    context_tokens = tokenizer.encode(context, add_special_tokens=False)
    concats = concat_question_and_endings(example.question, example.endings)
    longest_concat = concats[argmax(concats)]
    # get the longest span to test max length
    text_b_tokens = tokenizer.encode(longest_concat, add_special_tokens=False)
    return len(context_tokens) + len(text_b_tokens) > max_length


def create_windows(
    context: str,
    tokenizer: PreTrainedTokenizer,
    max_length: int,
    stride: int
) -> List[int]:
    context_tokens = tokenizer.encode(context, add_special_tokens=False)
    windows = []
    win_start = 0
    # three special tokens will be added, remove them from the count
    max_length -= 3
    win_end = max_length
    total_size = len(context_tokens)
    nof_windows = round(total_size / (max_length - stride))
    for _ in range(nof_windows):
        windows.append(context_tokens[win_start:win_end])
        win_start = win_end - stride
        win_end = min(win_start + max_length, total_size)

    return [
        tokenizer.decode(tokens, skip_special_tokens=True)
        for tokens in windows
    ]


def concat_question_and_endings(question: str, endings: List[str]) -> List[str]:
    concats = []
    for end in endings:
        if question.find("_") != -1:
            # this is for cloze question
            text_b = question.replace("_", end)
        else:
            text_b = question + " " + end
        concats.append(text_b)

    return concats


def create_input_features(
    contexts: List[str],
    endings: List[str],
    example_id: int,
    label: int,
    max_length: int,
    tokenizer: PreTrainedTokenizer,
) -> InputFeatures:
    choices_inputs = []
    for text_a, text_b in zip(contexts, endings):
        inputs = tokenizer(
            text_a,
            text_b,
            add_special_tokens=True,
            max_length=max_length,
            padding="max_length",
            truncation='only_first',
            return_overflowing_tokens=True,
        )
        if "num_truncated_tokens" in inputs and inputs["num_truncated_tokens"] > 0:
            logger.info(
                "Attention! you are cropping tokens (swag task is ok). "
                "If you are training ARC and RACE and you are poping question + options,"
                "you need to try to use a bigger max seq length!"
            )

        choices_inputs.append(inputs)

    input_ids = [x["input_ids"] for x in choices_inputs]
    attention_mask = (
        [x["attention_mask"] for x in choices_inputs] if "attention_mask" in choices_inputs[0] else None
    )
    token_type_ids = (
        [x["token_type_ids"] for x in choices_inputs] if "token_type_ids" in choices_inputs[0] else None
    )
    return InputFeatures(
        example_id=example_id,
        input_ids=input_ids,
        attention_mask=attention_mask,
        token_type_ids=token_type_ids,
        label=label,
    )


def windowed_tokenization(
    example: InputExample,
    label_map: dict,
    max_length: int,
    stride: int,
    no_answer_text: str,
    tokenizer: PreTrainedTokenizer,
    text_tokenizer: TextTokenizer,
    window_fn: Callable = None
) -> InputFeatures:
    # ToDo := Different amount of windows will trigger an error because of
    # different size in input features? sequences should be grouped by
    # size and chopped, padded accordingly
    window_fn = window_fn if window_fn is not None else create_windows
    window_texts = window_fn(
        example.contexts[0], tokenizer, max_length, stride
    )
    logger.info(f"Created {len(window_texts)} windows for `{example.example_id}` example")
    concats = concat_question_and_endings(example.question, example.endings)
    # win 1: end 1
    # win 1: end 2
    # ....
    # win n: end 1
    # win n: end m
    texts_a, texts_b = list(zip(*[
        (text_a, text_b) for text_a in window_texts for text_b in concats
    ]))
    return create_input_features(
        contexts=texts_a,
        endings=texts_b,
        example_id=example.example_id,
        label=label_map[example.label],
        max_length=max_length,
        tokenizer=tokenizer,
    )


def convert_examples_to_features(
    examples: List[InputExample],
    label_list: List[str],
    max_length: int,
    tokenizer: PreTrainedTokenizer,
    enable_window: bool = False,
    stride: int = None,
    no_answer_text: str = None,
    window_fn: Callable = None,
) -> List[InputFeatures]:
    """
    Loads a data file into a list of `InputFeatures`
    """
    if enable_window and (stride is None or no_answer_text is None):
        raise ValueError(
            'Windowing mechanism is activated, but no "stride" or '
            '"no answer text" was provided, please provide them or disable'
            'the mechanism with `enable_window=False`'
        )

    features = []
    label_map = {label: i for i, label in enumerate(label_list)}
    text_tokenizer = TextTokenizer()
    for (ex_index, example) in tqdm.tqdm(enumerate(examples), desc="convert examples to features"):
        if ex_index % 10000 == 0:
            logger.info("Writing example %d of %d" % (ex_index, len(examples)))

        if enable_window and should_window(example, tokenizer, max_length):
            feats = windowed_tokenization(
                example=example,
                label_map=label_map,
                max_length=max_length,
                stride=stride,
                no_answer_text=no_answer_text,
                tokenizer=tokenizer,
                text_tokenizer=text_tokenizer,
                window_fn=window_fn
            )
        else:
            concats = concat_question_and_endings(
                example.question, example.endings
            )
            feats = create_input_features(
                contexts=example.contexts,
                endings=concats,
                example_id=example.example_id,
                label=label_map[example.label],
                max_length=max_length,
                tokenizer=tokenizer,
            )

        features.append(feats)

    for f in features[:2]:
        logger.info("*** Example ***")
        logger.info("feature: %s" % f)

    return features