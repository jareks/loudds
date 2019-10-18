# Copyright 2019 by Jarosław Skrzypek. All rights reserved.

"""
Send predictions result from FastAI learner to your selected HTTP endpoint.

Sample usage:

learn = fastai.vision.cnn_learner(data, model, metrics=error_rate)
# train model...

summary = prepare_summary(learn, { DatasetType.Valid: 'validation' })
requests.post("http://1.2.3.4/endpoint", json=summary)
"""

from fastai.basic_data.DatasetType import DatasetType, Learner
from torch import Tensor

def _summary_part(classes: list, predictions: torch.Tensor, targets: torch.Tensor, losses: torch.Tensor,
                  dataset: fastai.basic_data.DeviceDataLoader, dataset_name: str):
    """ Returns summary of predictions against targets """

    items = []
    for i in range(len(dataset.items)):
      filename = dataset.items[i].name
      items.append({
          'predictions': { classes[j]: float(predictions[i][j]) for j in range(len(classes)) },
          'target': classes[targets[i]],
          'loss': losses[i].tolist(),
          'filename': filename,
          'type': dataset_name
      })
    return items

def prepare_summary(learner: fastai.basic_train.Learner, sets: dict = { DatasetType.Valid: 'validation', DatasetType.Test: 'test' }):
    """ Returns summary of predictions made by learner """

    classes = learn.data.classes
    summary = {
        'items': []
    }

    for ds_type, name in sets.items():
        predictions, targets, losses = learner.get_preds(ds_type=ds_type, with_loss=True)
        dataset = learn.data.dl(ds_type)
        summary['items'] += (_summary_part(classes, predictions, targets, losses, dataset, name))
    return summary

summary = prepare_summary(learn, { DatasetType.Valid: 'validation' })

