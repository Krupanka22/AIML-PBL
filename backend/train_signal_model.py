"""Train the supervised green-duration model."""
from control import MLGreenController


if __name__ == "__main__":
    controller = MLGreenController()
    controller.train()
    print("Trained ML signal model:", controller.model_path)
