import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import train_test_split
import pandas as pd
import matplotlib.pyplot as plt
import random

# Random seed
seed = 29
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

data = pd.read_csv('24data.csv', engine='python')

X = np.random.uniform(low=0, high=1, size=(data.shape[0], 24))  # Randomly generate white noise as input
y_scaled = data.iloc[:, :24].values  # The first 24 columns are the values to be predicted
conditions_scaled = data.iloc[:, 24:].values  # The following 30 columns are the condition parameters

# Split training and testing sets
X_train, X_test, y_train, y_test, conditions_train, conditions_test = train_test_split(
    X, y_scaled, conditions_scaled, test_size=0.2, random_state=seed
)

# Convert to Tensor
X_train_tensor = torch.FloatTensor(X_train)
y_train_tensor = torch.FloatTensor(y_train)
conditions_train_tensor = torch.FloatTensor(conditions_train)

X_test_tensor = torch.FloatTensor(X_test)
y_test_tensor = torch.FloatTensor(y_test)
conditions_test_tensor = torch.FloatTensor(conditions_test)

# Data loader
train_dataset = TensorDataset(X_train_tensor, conditions_train_tensor, y_train_tensor)
train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)

# Generator model
class Generator(nn.Module):
    def __init__(self, input_dim, condition_dim, output_dim):
        super(Generator, self).__init__()
        self.fc_layers = nn.Sequential(
            nn.Linear(input_dim + condition_dim, 128),
            nn.LeakyReLU(0.2),
            nn.Dropout(0.2),
            nn.Linear(128, 256),
            nn.LeakyReLU(0.2),
            nn.Dropout(0.2),
            nn.Linear(256, 512),
            nn.LeakyReLU(0.2),
            nn.Dropout(0.2),
            nn.Linear(512, output_dim)
        )

        self.conv_layers = nn.Sequential(
            nn.Conv1d(in_channels=1, out_channels=32, kernel_size=3, padding=1, stride=1),
            nn.LeakyReLU(0.2),
            nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1, stride=1),
            nn.LeakyReLU(0.2),
            nn.Conv1d(in_channels=64, out_channels=32, kernel_size=3, padding=1, stride=1),
            nn.LeakyReLU(0.2),
            nn.Conv1d(in_channels=32, out_channels=1, kernel_size=3, padding=1, stride=1),
            nn.LeakyReLU(0.2),
        )

    def forward(self, z, condition):
        x = torch.cat([z, condition], dim=1)
        x = self.fc_layers(x)
        x = x.view(x.size(0), 1, 24)  # (batch_size, 1, 512)
        x = self.conv_layers(x)
        x = x.squeeze(1)
        return x

# Discriminator model
class Discriminator(nn.Module):
    def __init__(self, output_dim, condition_dim):
        super(Discriminator, self).__init__()
        self.model = nn.Sequential(
            nn.Linear(output_dim + condition_dim, 128),
            nn.LeakyReLU(0.2),
            nn.Linear(128, 64),
            nn.LeakyReLU(0.2),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )

    def forward(self, outputs, conditions):
        x = torch.cat((outputs, conditions), dim=1)
        return self.model(x)

# Create generator and discriminator
input_dim = X_train_tensor.shape[1]  # Dimension of white noise
condition_dim = conditions_train_tensor.shape[1]  # Dimension of condition parameters
output_dim = y_train_tensor.shape[1]  # Dimension of predicted output

generator = Generator(input_dim, condition_dim, output_dim)
discriminator = Discriminator(output_dim, condition_dim)

# Loss functions
adversarial_loss = nn.BCELoss()
regression_loss = nn.MSELoss()

# Optimizers
optimizer_G = torch.optim.Adam(generator.parameters(), lr=0.001, betas=(0.5, 0.999))
optimizer_D = torch.optim.Adam(discriminator.parameters(), lr=0.001, betas=(0.5, 0.999))

# Evaluation metrics calculation function
def evaluate_metrics(y_true, y_pred):
    r2 = r2_score(y_true, y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    return r2, mae, rmse

# Evaluate metrics for each dimension
def evaluate_metrics_per_dimension(y_true, y_pred):
    r2_list, mae_list, rmse_list = [], [], []
    for i in range(y_true.shape[1]): 
        r2 = r2_score(y_true[:, i], y_pred[:, i])
        mae = mean_absolute_error(y_true[:, i], y_pred[:, i])
        rmse = np.sqrt(np.mean((y_true[:, i] - y_pred[:, i]) ** 2))
        r2_list.append(r2)
        mae_list.append(mae)
        rmse_list.append(rmse)
    return r2_list, mae_list, rmse_list

# Train CGAN
epochs = 5001

for epoch in range(epochs):
    for real_inputs, conditions, real_outputs in train_loader:
        batch_size = real_inputs.size(0)

        # Labels
        real_labels = torch.ones(batch_size, 1)
        fake_labels = torch.zeros(batch_size, 1)

        # Train the discriminator
        optimizer_D.zero_grad()
        real_outputs_pred = discriminator(real_outputs, conditions)
        d_loss_real = adversarial_loss(real_outputs_pred, real_labels)

        noise = real_inputs  # Use white noise
        fake_outputs = generator(noise, conditions)
        fake_outputs_pred = discriminator(fake_outputs, conditions)
        d_loss_fake = adversarial_loss(fake_outputs_pred, fake_labels)
        d_loss = d_loss_real + d_loss_fake
        d_loss.backward()
        optimizer_D.step()

        # Train the generator
        optimizer_G.zero_grad()
        fake_outputs = generator(noise, conditions)
        fake_outputs_pred = discriminator(fake_outputs, conditions)
        g_loss_adversarial = adversarial_loss(fake_outputs_pred, real_labels)
        g_loss_regression = regression_loss(fake_outputs, real_outputs)
        g_loss = g_loss_adversarial + g_loss_regression
        g_loss.backward()
        optimizer_G.step()

    if epoch % 100 == 0:
        generator.eval()
        with torch.no_grad():
            y_pred_test = generator(X_test_tensor, conditions_test_tensor).numpy()

            y_test = y_test_tensor.numpy()

            r2_test, mae_test, rmse_test = evaluate_metrics(y_test, y_pred_test)
            print(
                f"Epoch [{epoch}/{epochs}] - Test Set Evaluation: R²: {r2_test:.4f}, MAE: {mae_test:.4f}, RMSE: {rmse_test:.4f}")

# Save the generator and discriminator model parameters
torch.save(generator.state_dict(), "generator_model0.2.pth")
torch.save(discriminator.state_dict(), "discriminator_model0.2.pth")


with torch.no_grad():
    # Test set
    y_pred_test = generator(X_test_tensor, conditions_test_tensor).numpy()
    y_test = y_test_tensor.numpy()
    results_df = pd.DataFrame(
        y_pred_test,  # 24-dimensional prediction results
        columns=["AI", "Arms", "Ars", "ASI", "CAI", "CAV", "Drms", "Drs", "EPA", "EPV", "Ia", "Ic", "Id", "If",
                 "Iv", "PGA", "PGD", "PGV", "PSA", "PSV", "Td", "Vrms", "Vrs", "VSI"]
    )
    # Save to CSV file
    results_df.to_csv('test_predictions.csv', index=False)

    r2_test, mae_test, rmse_test = evaluate_metrics(y_test, y_pred_test)
    print(f"Test Set Evaluation: R²: {r2_test:.4f}, MAE: {mae_test:.4f}, RMSE: {rmse_test:.4f}")
    r2_test_per_dim, mae_test_per_dim, rmse_test_per_dim = evaluate_metrics_per_dimension(y_test, y_pred_test)
    print("Test Set Evaluation per Dimension:")
    for i in range(output_dim):
        print(f"Dimension {results_df.columns[i]}: R²: {r2_test_per_dim[i]:.4f}, MAE: {mae_test_per_dim[i]:.4f}, RMSE: {rmse_test_per_dim[i]:.4f}")

    # Training set
    y_pred_train = generator(X_train_tensor, conditions_train_tensor).numpy()
    y_train = y_train_tensor.numpy()
    results_train_df = pd.DataFrame(
        y_pred_train,  # 24-dimensional prediction results
        columns=["AI", "Arms", "Ars", "ASI", "CAI", "CAV", "Drms", "Drs", "EPA", "EPV", "Ia", "Ic", "Id", "If",
                 "Iv", "PGA", "PGD", "PGV", "PSA", "PSV", "Td", "Vrms", "Vrs", "VSI"]
    )
    results_train_df.to_csv('train_predictions.csv', index=False)

    # Training set evaluation metrics
    r2_train, mae_train, rmse_train = evaluate_metrics(y_train, y_pred_train)
    print(f"\nTrain Set Evaluation: R²: {r2_train:.4f}, MAE: {mae_train:.4f}, RMSE: {rmse_train:.4f}")
    r2_train_per_dim, mae_train_per_dim, rmse_train_per_dim = evaluate_metrics_per_dimension(y_train, y_pred_train)
    print("Train Set Evaluation per Dimension:")
    for i in range(output_dim):
        print(f"Dimension {results_train_df.columns[i]}: R²: {r2_train_per_dim[i]:.4f}, MAE: {mae_train_per_dim[i]:.4f}, RMSE: {rmse_train_per_dim[i]:.4f}")

# Iterate over all dimensions
for i in range(24): 
    true_values = y_test[:, i]
    predicted_values = y_pred_test[:, i]

    plt.figure(figsize=(10, 6))

    plt.scatter(true_values, predicted_values, color='blue', alpha=0.5, label='Testing')
    min_val = min(np.min(true_values), np.min(predicted_values))
    max_val = max(np.max(true_values), np.max(predicted_values))
    plt.plot([min_val, max_val], [min_val, max_val], color='red', linestyle='dashed', label='Ideal Fit')

    # Set logarithmic scale
    plt.xscale('log')
    plt.yscale('log')

    # Set labels
    plt.xlabel(f'Observed: {results_df.columns[i]}')
    plt.ylabel(f'Predicted: {results_df.columns[i]}')
    plt.legend()
    plt.savefig(f"test_dim_{results_df.columns[i]}.png")
    plt.close()

for i in range(24): 
    true_values = y_train[:, i]
    predicted_values = y_pred_train[:, i]

    plt.figure(figsize=(10, 6))

    plt.scatter(true_values, predicted_values, color='blue', alpha=0.5, label='Training')
    min_val = min(np.min(true_values), np.min(predicted_values))
    max_val = max(np.max(true_values), np.max(predicted_values))
    plt.plot([min_val, max_val], [min_val, max_val], color='red', linestyle='dashed', label='Ideal Fit')

    # Set logarithmic scale
    plt.xscale('log')
    plt.yscale('log')

    # Set labels
    plt.xlabel(f'Observed: {results_train_df.columns[i]}')
    plt.ylabel(f'Predicted: {results_train_df.columns[i]}')
    plt.legend()
    plt.savefig(f"train_dim_{results_train_df.columns[i]}.png")
    plt.close()
