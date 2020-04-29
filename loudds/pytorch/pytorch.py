import torch
from pathlib import Path


def summary_for_image_folder(image_folder, model, loss_fn, batch_size=32):
    classes = image_folder.classes
    loader = torch.utils.data.DataLoader(image_folder, shuffle=False, batch_size=32)
    items = []
    model.eval()
    is_cuda = next(model.parameters()).is_cuda

    with torch.no_grad():
        batch_start = 0

        # Disable original loss_fn reduction to get loss for every single case
        original_reduction = loss_fn.reduction
        try:
            loss_fn.reduction = "none"
            for (inputs, labels) in loader:
                if is_cuda:
                    inputs = inputs.to("cuda")
                    labels = labels.to("cuda")
                outputs = model(inputs)
                losses = loss_fn(outputs, labels)
                _, predictions = torch.max(outputs, 1)

                for in_batch in range(len(inputs)):
                    filename = Path(image_folder.imgs[batch_start + in_batch][0]).name
                    items.append(
                        {
                            "predictions": {
                                classes[j]: float(outputs[in_batch][j].item())
                                for j in range(len(classes))
                            },
                            "target": classes[labels[in_batch]],
                            "loss": losses[in_batch].item(),
                            "filename": filename,
                            "type": "???",
                        }
                    )
                batch_start += len(inputs)
        finally:
            loss_fn.reduction = original_reduction
    return {"items": items}


def summary_for_regression(dataset_item_ids, x, y, model, loss_fn):
    assert len(dataset_item_ids) == len(x) == len(y)

    items = []
    with torch.no_grad():
        pred_y = model(x)

        # Disable original loss_fn reduction to get loss for every single case
        original_reduction = loss_fn.reduction
        try:
            loss_fn.reduction = "none"
            losses = loss_fn(pred_y, y)
        finally:
            loss_fn.reduction = original_reduction

        for i in range(len(x)):
            items.append(
                {
                    "target": y[i].item(),
                    "prediction": pred_y[i].item(),
                    "loss": losses[i],
                    "dataset_item_id": dataset_item_ids[i],
                }
            )

    return {"items": items}
