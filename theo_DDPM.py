import math
from theo_unet import UNet

import torch
import torch.nn as nn


class DDPM(nn.Module):
    def __init__(self, image_size, ctx_sz=1, timesteps=1000, unet_stages=3):
        super().__init__()
        self.timesteps = timesteps
        self.image_size = image_size
        self.model = UNet(unet_stages, ctx_sz)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.register_buffer("betas", _cosine_variance_schedule(timesteps))
        self.register_buffer("alphas", 1.0 - self.betas)
        self.register_buffer("alphas_cumprod", self.alphas.cumprod(dim=-1))
        self.register_buffer("sqrt_alphas_cumprod", self.alphas_cumprod.sqrt())
        self.register_buffer(
            "sqrt_one_minus_alphas_cumprod", (1.0 - self.alphas_cumprod).sqrt()
        )

    def train(self, clean_image: torch.Tensor):
        """Train the model on a batch of clean images, letting the model predict the noise and returning the MSE. Minimize the output directly."""
        noise = torch.randn_like(clean_image)
        t = torch.randint(0, self.timesteps, (clean_image.shape[0],)).to(
            clean_image.device
        )

        image_scale = self.sqrt_alphas_cumprod.gather(-1, t).reshape(
            clean_image.shape[0], 1, 1, 1
        )
        noise_scale = self.sqrt_one_minus_alphas_cumprod.gather(-1, t).reshape(
            clean_image.shape[0], 1, 1, 1
        )

        noisy = image_scale * clean_image + noise_scale * noise

        pred_noise = self.model(noisy, t.unsqueeze(1).float())

        return torch.mean((pred_noise - noise) ** 2)

    @torch.no_grad()
    def sample(self, amount : int, whole_process : bool) -> torch.Tensor:
        """Sample from the model."""
        # sample noise from standard normal distribution
        image = torch.randn((amount, 1, self.image_size, self.image_size)).to(self.device).float()

        images = []

        for t in range(self.timesteps-1, 0, -1):
            step = t * torch.ones(amount, dtype=int).to(self.device)
            images.append(image)
            image : torch.Tensor = self.reverse_diffusion(image, step)

        if whole_process:
            # images holds the images from the noisiest to the denoised image
            # concatenate each step into one image for for each sample
            images = torch.cat(images[::10], dim=2)
            return images

        else: 
            return image
    

    @torch.no_grad()
    def reverse_diffusion(self, x_t: torch.Tensor, t : torch.Tensor) -> torch.Tensor:
        """
        p(x_{t-1}|x_{t})-> mean,std

        pred_noise-> pred_mean and pred_std
        """
        pred = self.model(x_t, t.unsqueeze(1).float())

        batch_size: int = x_t.shape[0]
        alpha_t = self.alphas.gather(-1, t).reshape(batch_size, 1, 1, 1)
        alpha_t_cumprod = self.alphas_cumprod.gather(-1, t).reshape(batch_size, 1, 1, 1)
        beta_t = self.betas.gather(-1, t).reshape(batch_size, 1, 1, 1)
        sqrt_one_minus_alpha_cumprod_t = self.sqrt_one_minus_alphas_cumprod.gather(
            -1, t
        ).reshape(batch_size, 1, 1, 1)
        mean = (1.0 / torch.sqrt(alpha_t)) * (
            x_t - ((1.0 - alpha_t) / sqrt_one_minus_alpha_cumprod_t) * pred
        )

        if t.min() > 0:
            alpha_t_cumprod_prev = self.alphas_cumprod.gather(-1, t - 1).reshape(
                batch_size, 1, 1, 1
            )
            std = torch.sqrt(
                beta_t * (1.0 - alpha_t_cumprod_prev) / (1.0 - alpha_t_cumprod)
            )
        else:
            std = 0.0

        noise = torch.randn_like(x_t)
        return mean + std * noise


def _cosine_variance_schedule(timesteps, epsilon=0.008):
    steps = torch.linspace(0, timesteps, steps=timesteps + 1, dtype=torch.float32)
    f_t = (
        torch.cos(((steps / timesteps + epsilon) / (1.0 + epsilon)) * math.pi * 0.5)
        ** 2
    )
    betas = torch.clip(1.0 - f_t[1:] / f_t[:timesteps], 0.0, 0.999)

    return betas
