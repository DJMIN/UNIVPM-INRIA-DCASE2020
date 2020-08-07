import numpy as np
from torch.utils.data import Dataset
from .augmentations import apply_augmentation_chain
from .feats_utils import choose_feats
from .feats_utils import choose_background, downsample, normalize, get_feats
import soundfile as sf
import torch

class UnlabeledSet(Dataset):

    def __init__(self, weak, cfg, time_augment=True, backgrounds=None, rirs=None, return_sources=False):

        self.feats_func = choose_feats(cfg["feats"])
        self.confs = cfg
        self.weak = weak
        self.time_augment = time_augment
        self.backgrounds = backgrounds
        self.rirs = rirs
        self.return_sources = return_sources

    def __len__(self):
        return len(self.weak)


    def __getitem__(self, item):

        c_ex = self.weak[item] # we sample a weak wav + its weak labels

        audio , fs = sf.read(c_ex)
        if len(audio.shape) > 1:
            audio = audio[:, np.random.randint(0, audio.shape[-1] -1)]
        audio = downsample(np.asfortranarray(audio), fs)
        audio = audio - np.mean(audio) # zero mean

        # time-domain-augment
        if self.time_augment: # we return both strong and weak augmentations
            mixture_weak = apply_augmentation_chain(audio, self.confs["augmentations"]["unlabeled"]["weak_time"])
            # for strong augmentation we allow additional reverberation and an additional background
            if np.random.rand() < self.confs["augmentations"]["unlabeled"]["strong_time"]["add_reverb"]:
                mixture_strong = apply_augmentation_chain(audio, self.confs["augmentations"]["unlabeled"]["strong_time"], self.rirs)
            else:
                mixture_strong = apply_augmentation_chain(audio, self.confs["augmentations"]["unlabeled"]["strong_time"])
        else:
            mixture_weak = audio
            mixture_strong = np.copy(audio)

        # add additional background
        if self.time_augment:
            if np.random.rand() < self.confs["augmentations"]["unlabeled"]["strong_time"]["add_background"]:
                background = choose_background(self.backgrounds, None, target_len=len(mixture_strong))
                lvl = 20 * np.log10(np.max(np.abs(mixture_strong)))
                # because some files are basically all zeros (2 files)
                try:
                    target_lvl = np.random.uniform(lvl - 30, lvl)
                except:
                    target_lvl = np.random.uniform(-45, 0)  # all zeros we add only background
                mixture_strong = mixture_strong + normalize(background, target_lvl)  # we limit how much strong could be

            # random gain
            mixture_weak = normalize(mixture_weak, np.clip(np.random.normal(-30, 7), -45, 0))
            mixture_strong = normalize(mixture_strong, np.clip(np.random.normal(-30, 7), -45, 0))

        # feature extraction and random augment
        target_frames = self.confs["feats"]["max_len"]

        mixture_weak = get_feats(self.feats_func, mixture_weak, target_frames)
        mixture_strong = get_feats(self.feats_func, mixture_strong, target_frames)

        mixture_weak = apply_augmentation_chain(mixture_weak, self.confs["augmentations"]["unlabeled"]["weak_feats"])  # augment feats
        mixture_strong = apply_augmentation_chain(mixture_strong, self.confs["augmentations"]["unlabeled"]["strong_feats"])



        if not self.return_sources:

            max_len_targets = self.confs["feats"]["max_len"] // self.confs["net"]["pool_factor"]
            strong = torch.zeros(max_len_targets, self.confs["data"]["n_classes"])
            weak = torch.zeros(self.confs["data"]["n_classes"])

            mask_weak = torch.zeros([1]).bool()
            mask_strong = torch.zeros([1]).bool()

            return torch.from_numpy(mixture_weak.T).float(), torch.from_numpy(mixture_strong.T).float(), strong , weak, mask_strong, mask_weak
        else:

            sources_weak = torch.zeros((self.confs["data"]["max_n_sources"], target_frames, mixture_weak.shape[0]))
            # fake sources
            sources_strong = sources_weak

            max_len_targets = self.confs["feats"]["max_len"] // self.confs["net"]["pool_factor"]
            strong = torch.zeros(self.confs["data"]["max_n_sources"], max_len_targets, self.confs["data"]["n_classes"])
            weak = torch.zeros(self.confs["data"]["max_n_sources"], self.confs["data"]["n_classes"])

            mask_weak = torch.zeros([1]).bool()
            mask_strong = torch.zeros([1]).bool()


            return torch.from_numpy(mixture_weak.T).float(), sources_weak, torch.from_numpy(
                mixture_strong.T).float(), sources_strong, strong, weak, mask_strong, mask_weak