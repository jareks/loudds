# Copyright 2019 by Jarosław Skrzypek. All rights reserved.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
Send predictions result from FastAI learner to your selected HTTP endpoint.

Sample usage:

import loudds.fastai as loud

learn = fastai.vision.cnn_learner(data, model, metrics=error_rate)
# train model...

summary = loud.prepare_summary(learn, { DatasetType.Valid: 'validation' })
requests.post("http://1.2.3.4/endpoint", json=summary, headers={'Authorization': f"bearer {LOUDDATA_TOKEN}"})
"""

from fastai.basic_data import DatasetType, DeviceDataLoader
from fastai.vision import Learner
from torch import Tensor


def _summary_part(
    classes: list,
    predictions: Tensor,
    targets: Tensor,
    losses: Tensor,
    dataset: DeviceDataLoader,
    dataset_name: str,
):
    """ Returns summary of predictions against targets """

    items = []
    for i in range(len(dataset.items)):
        filename = dataset.items[i].name
        items.append(
            {
                "predictions": {
                    classes[j]: float(predictions[i][j]) for j in range(len(classes))
                },
                "target": classes[targets[i]],
                "loss": losses[i].tolist(),
                "filename": filename,
                "type": dataset_name,
            }
        )
    return items


def prepare_summary(
    learner: Learner,
    sets: dict = {DatasetType.Valid: "validation", DatasetType.Test: "test"},
):
    """ Returns summary of predictions made by learner """

    classes = learner.data.classes
    summary = {"items": []}

    for ds_type, name in sets.items():
        predictions, targets, losses = learner.get_preds(
            ds_type=ds_type, with_loss=True
        )
        dataset = learner.data.dl(ds_type)
        summary["items"] += _summary_part(
            classes, predictions, targets, losses, dataset, name
        )
    return summary
