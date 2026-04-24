"""Fine-tune DistilBERT for intent classification.

Reads JSONL from ml/data/intents_sample.jsonl, stratified 80/20 split,
trains for 4 epochs, logs metrics + model artifact to MLflow, and saves
the serving-ready model to settings.intent_model_path.

Run inside the container:
    python -m app.scripts.train_intent
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
from sklearn.metrics import classification_report, f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger("train_intent")

DATA_PATH = Path("ml/data/intents_sample.jsonl")
MODEL_OUT = Path(settings.intent_model_path)
BASE_MODEL = "distilbert-base-uncased"
EPOCHS = 4
BATCH = 16
LR = 2e-5
MAX_LEN = 64


def _load() -> tuple[list[str], list[str]]:
    texts, labels = [], []
    with DATA_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(row["label"])
    return texts, labels


def main() -> None:
    configure_logging()
    # Heavy imports kept inside main() so non-training containers don't pay
    # the cold-start cost.
    import torch
    from torch.utils.data import Dataset
    from transformers import (
        AutoTokenizer,
        DistilBertForSequenceClassification,
        Trainer,
        TrainingArguments,
    )

    texts, labels = _load()
    label_list = sorted(set(labels))
    label2id = {l: i for i, l in enumerate(label_list)}
    id2label = {i: l for l, i in label2id.items()}
    y = np.array([label2id[l] for l in labels])
    log.info("data_loaded", n=len(texts), classes=label_list)

    tr_texts, ev_texts, tr_y, ev_y = train_test_split(
        texts, y, test_size=0.2, random_state=42, stratify=y
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    class _DS(Dataset):                                                       # type: ignore[misc]
        def __init__(self, texts: list[str], ys: np.ndarray) -> None:
            self.enc = tokenizer(
                texts,
                truncation=True,
                padding="max_length",
                max_length=MAX_LEN,
                return_tensors="pt",
            )
            self.ys = torch.tensor(ys, dtype=torch.long)

        def __len__(self) -> int:
            return len(self.ys)

        def __getitem__(self, i: int) -> dict[str, Any]:
            return {
                "input_ids": self.enc["input_ids"][i],
                "attention_mask": self.enc["attention_mask"][i],
                "labels": self.ys[i],
            }

    tr_ds, ev_ds = _DS(tr_texts, tr_y), _DS(ev_texts, ev_y)

    model = DistilBertForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(label_list),
        label2id=label2id,
        id2label=id2label,
    )

    def _metrics(pred: Any) -> dict[str, float]:
        preds = pred.predictions.argmax(-1)
        p, r, f1, _ = precision_recall_fscore_support(
            pred.label_ids, preds, average="macro", zero_division=0
        )
        return {"precision": float(p), "recall": float(r), "f1_macro": float(f1)}

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(
        output_dir=str(MODEL_OUT.with_suffix(".ckpt")),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH,
        per_device_eval_batch_size=BATCH,
        learning_rate=LR,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        logging_steps=10,
        report_to=[],
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tr_ds,
        eval_dataset=ev_ds,
        compute_metrics=_metrics,
    )

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("intent_classifier")
    with mlflow.start_run() as run:
        mlflow.log_params({
            "base": BASE_MODEL, "epochs": EPOCHS, "batch": BATCH,
            "lr": LR, "max_len": MAX_LEN, "n_train": len(tr_ds),
        })
        trainer.train()
        eval_out = trainer.evaluate()
        mlflow.log_metrics({k: v for k, v in eval_out.items() if isinstance(v, float)})

        preds = trainer.predict(ev_ds).predictions.argmax(-1)
        report = classification_report(
            ev_y, preds, target_names=label_list, zero_division=0
        )
        log.info("eval_report", report=report)
        (MODEL_OUT.parent / "report.txt").write_text(report)
        mlflow.log_text(report, "classification_report.txt")

        trainer.save_model(str(MODEL_OUT))
        tokenizer.save_pretrained(str(MODEL_OUT))
        log.info(
            "model_saved",
            path=str(MODEL_OUT),
            f1_macro=round(f1_score(ev_y, preds, average="macro"), 3),
            run_id=run.info.run_id,
        )


if __name__ == "__main__":
    main()
