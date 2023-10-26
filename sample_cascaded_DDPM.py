import argparse
import shutil
import numpy as np

import torch
import utils
import os
from models.DDPM_big import DDPM_big
from models.DDPM import DDPM
import torchvision

def parse_args():
    parser = argparse.ArgumentParser(description="Training MNISTDiffusion")

    parser.add_argument(
        "--size",
        type=int,
        help="stotal amount of data",
        default=100,
    )

    parser.add_argument("--small_name", type=str, help="define run name", required=True)
    parser.add_argument("--big_name", type=str, help="define run name", required=True)
    
    args = parser.parse_args()

    parse_add_txt(args.small_name, args)
    parse_add_txt(args.big_name, args)

    # print(args)
    return args

def parse_add_txt(run_name, args):
    # load run_name/args.txt file and parse:
    args_file = "checkpoints/{}/args.txt".format(run_name)
    argsDict = {}
    with open(args_file, "r") as f:
        for l in f.readlines():
            k, v = l.split()
            k = k.replace("--", "", 1) # remove first occurence of "--"
            value = v
            try:
                value = eval(v)
            except:
                pass
            argsDict[run_name + k] = value

    # overwrite args with args from args.txt:
    for k, v in argsDict.items():
        setattr(args, k, v)


# checkpoints name is model_<i>.pth

def main(args):

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # extract small model args:
    small_img_size = getattr(args, args.small_name + "img_size")

    small_states = getattr(args, args.small_name + "markov_states")
    small_unet_stages = getattr(args, args.small_name + "unet_stages")
    small_noise_power = getattr(args, args.small_name + "noise_power")

    # load small model from checkpoint folder:
    small = utils.load_checkpoint(DDPM(small_img_size, 11, small_states, small_unet_stages, small_noise_power), args.small_name).to(device)

    # extract big model args:
    big_img_size = getattr(args, args.big_name + "img_size")

    big_states = getattr(args, args.big_name + "markov_states")
    big_unet_stages = getattr(args, args.big_name + "unet_stages")
    big_noise_power = getattr(args, args.big_name + "noise_power")

    # load big model from checkpoint folder:
    big = utils.load_checkpoint(DDPM_big(big_img_size, 11, big_states, big_unet_stages, big_noise_power), args.big_name).to(device)

    small_samples, big_samples = sample(30, small, big, torch.arange(30) % 10)

    small_samples_resized = torchvision.transforms.Resize(big.image_size, antialias=True)(small_samples)


    stacked = torch.cat([small_samples_resized, big_samples], dim=2)

    name = f"{args.small_name}_to_{args.big_name}"
    torchvision.utils.save_image(stacked, name+".png", nrow=10, padding=15)

    print("saved cascaded sample preview to {}".format(name))


    # delete files in output directory if it already exists:
    shutil.rmtree("synthesized/{}".format(name), ignore_errors=True)
    # create output directory:
    os.makedirs("synthesized/{}".format(name), exist_ok=True)

    batch_size = 64

    images = []
    labels = []

    for i in range(args.size // batch_size):
        print(f"Sampling batch {1+i} / {args.size // batch_size}")

        gen_labels = torch.randint(0, 10, (batch_size,)).to(device).tolist()

        _small, samples = sample(batch_size, small, big, target_label=gen_labels)
        samples = samples.cpu().numpy()

        images.append(samples)
        labels.append(gen_labels)
        
    images = np.concatenate(images, axis=0)
    labels = np.concatenate(labels, axis=0)

    np.save(f"synthesized/{name}/images.npy", images)
    np.save(f"synthesized/{name}/labels.npy", labels)

    print("saved cascaded samples to synthesized/{} directory".format(name))


    n = 100
    print(f"sampling {n} images to see how fast it goes:")
    import time


    start = time.time()
    for i in range(n//2):
        gen_labels = torch.randint(0, 10, (2,)).tolist()

        _small_sample, big_samples = sample(2, small, big, target_label=gen_labels)

    end = time.time()
    print(f"{n} samples took {end - start} seconds, which is an average of {(end - start) / n} seconds per sample")


@torch.no_grad()
def sample(amount : int, small_model : DDPM, big_model : DDPM_big, target_label : list):
    
    small_samples = small_model.sample(amount, target_label, keep_intermediate=False)
    small_samples_resized = torchvision.transforms.Resize(big_model.image_size, antialias=True)(small_samples)
    big_samples = big_model.sample(amount, target_label, small_samples_resized, keep_intermediate=False)

    return small_samples, big_samples


if __name__ == "__main__":
    args = parse_args()
    main(args)