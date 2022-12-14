<div align="center">
<h1>transcript_transformer</h1> 

Deep learning utility functions for processing and annotating transcript genome data.

[![PyPi Version](https://img.shields.io/pypi/v/transcript-transformer.svg)](https://pypi.python.org/pypi/transcript-transformer/)
[![GitHub license](https://img.shields.io/github/license/jdcla/transcript_transformer)](https://github.com/jdcla/transcript_transformer/blob/main/LICENSE.md)
[![GitHub issues](https://img.shields.io/github/issues/jdcla/transcript_transformer)](https://github.com/jdcla/transcript_transformer/issues)
[![GitHub stars](https://img.shields.io/github/stars/jdcla/transcript_transformer)](https://github.com/jdcla/transcript_transformer/stargazers)
</div>


`transcript_transformer`  is constructed in concordance with the creation of TIS Transformer, ([paper](https://www.biorxiv.org/content/10.1101/2021.11.18.468957v2), [repository](https://github.com/jdcla/TIS_transformer)) and RIBO-former (to be released). `transcript_transformer` makes use of the [Performer](https://arxiv.org/abs/2009.14794) architecture to allow for the annotations and processing of transcripts at single nucleotide resolution. The package makes use of `h5py` for data loading and `pytorch-lightning` as a high-level interface for training and evaluation for deep learning models. `transcript_transformer` is designed to allow a high degree of modularity, but has not been tested for every combination of arguments, and can therefore return errors.

## 🔗 Installation
`pytorch` needs to be separately [installed by the user](https://pytorch.org/get-started/locally/). 

Next, the package can be installed running 
```bash
pip install transcript-transformer
```

## 📖 User guide <a name="code"></a>

The library features a tool that can be called directly by the command `transcript_transformer`, featuring three main functions: `pretrain`, `train` and `predict`. Data loading is achieved using the `h5` format, handled by the `h5py` package.

### Data loading
 Information is separated by transcript and information type. Information belonging to a single transcript is mapped according to the index they populate within each `h5py.dataset`, used to store different types of information. [Variable length arrays](https://docs.h5py.org/en/stable/special.html#arbitrary-vlen-data) are used to store the sequences and annotations of all transcripts under a single data set. 
Sequences are stored using integer arrays following: `{A:0, T:1, C:2, G:3, N:4}`
An example `data.h5` has the following structure:


```
data.h5                                     (h5py.file)
    transcript                              (h5py.group)
    ├── tis                                 (h5py.dataset, dtype=vlen(int))
    ├── contig                              (h5py.dataset, dtype=str)
    ├── id                                  (h5py.dataset, dtype=str)
    ├── seq                                 (h5py.dataset, dtype=vlen(int))
    ├── ribo                                (h5py.group)
    │   ├── SRR0000001                      (h5py.group)
    │   │   ├── 5                           (h5py.group)
    │   │   │   ├── data                    (h5py.dataset, dtype=vlen(int))
    │   │   │   ├── indices                 (h5py.dataset, dtype=vlen(int))
    │   │   │   ├── indptr                  (h5py.dataset, dtype=vlen(int))
    │   │   │   ├── shape                   (h5py.dataset, dtype=vlen(int))
    │   ├── ...
    │   ....
    
```

Ribosome profiling data is saved by reads mapped to each transcript position. Mapped reads are furthermore separated by their read lengths. As ribosome profiling data is often sparse, we made use of `scipy.sparse` to save data within the `h5` format. This allows us to save space and store matrix objects as separate arrays. Saving and loading of the data is achieved using the [h5max](https://github.com/jdcla/h5max) package.

<div align="center">
<img src="https://github.com/jdcla/h5max/raw/main/h5max.png" width="600">
</div>

Dictionary `.json` files are used to specify the application of data to `transcript_transformer`. When no sequence information or ribosome profiling data is used, either entry `seq` or `ribo` is set to `false`. For each ribosome profiling dataset, custom [P-site offsets](https://plastid.readthedocs.io/en/latest/glossary.html#term-P-site-offset) can be set per read length. 

```json
{
  "h5_path":"data.h5",
  "exp_path":"transcript",
  "y_path":"tis",
  "chrom_path":"contig",
  "id_path":"id",
  "seq":"seq",
  "ribo": {
    "SRR000001/5": {
      "25": 7,
      "26": 7,
      "27": 8,
      "28": 10,
      "29": 10,
      "30": 11,
      "31": 11,
      "32": 7,
      "33": 7,
      "34": 9,
      "35": 9,
    }
  }
}
```



### pretrain


Conform with transformers trained for natural language processing objectives, models can first be trained following a self-supervised learning objective. Using a masked language modelling approach, models are tasked to predict the classes of the masked input tokens. As such, a model is trained the 'semantics' of transcript sequences. The approach is similar to the one described by [Zaheer et al. ](https://arxiv.org/abs/2007.14062). This approach has not been using ribosome profiling data.


```
transcript_transformer pretrain -h

positional arguments:
    input_data            path to json file specifying input data (see README.md)
    val                   list of chromosomes used for the validation set
    test                  list of chromosomes used for the test set
  --mask_frac float       fraction of input positions that are masked (default: 0.85)
  --rand_frac float       fraction of masked inputs that are randomized (default: 0.1)
```

Example

```
transcript_transformer pretrain input_data.json --val 1 13 --test 2 14 --max_epochs 70 --gpu 1 
```

</details>

### train
The package supports training the models architectures listed under `transcript_transformer/models.py`. The function expects a `.json` file containing the input data info (see [data loading](https://github.com/jdcla/transcript_transformer#data-loading)). It is possible to start training upon pre-trained models using the `--transfer_checkpoint` functionality.


```
transcript_transformer train -h
    
positional arguments:
  dict_path               dictionary (json) path containing input data file info

options:
  --val                   contigs in data_path folder used for validation (default: None)
  --test                  contigs in data_path folder used for testing (default: None)
  --ribo_offset           offset mapped ribosome reads by read length (default: False)
  --name                  name of the model (default: )
  --log_dir               log dir (default: lightning_logs)
  --transfer_checkpoint   Path to checkpoint pretrained model (default: None)
```

Example

```
transcript_transformer train input_data.json --val 1 13 --test 2 14 --max_epochs 70 --transfer_checkpoint lightning_logs/mlm_model/version_0/ --name experiment_1 --gpu 1 
```

### predict

The predict function returns probabilities for all nucleotide positions on the transcript and can be saved using the `.npy` or `.h5` format. In addition to reading from `.h5` files, the function supports the use of a single RNA sequence as input or a path to a `.fa` file. Note that `.fa` and `.npy` formats are only supported for models that only apply transcript nucleotide information.

```
transcript_transformer predict -h

positional arguments:
  input_data            path to JSON dict (h5) or fasta file, or RNA sequence
  input_type            type of input
  checkpoint            path to checkpoint of trained model

options:
  -h, --help            show this help message and exit
  --test                contigs to predict on (h5 input format only) (default: None)
  --ribo_offset         offset mapped ribosome reads by read length (default: False)
  --output_type         file type of output predictions (default: npy)
  --save_path           save file path (default: results)
```


Example

```
transcript_transformer predict AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACGGT RNA --output_type npy models/example_model.ckpt
transcript_transformer predict data/example_data.fa fa --output_type npy models/example_model.ckpt
```

### Output data

The model returns predictions for every nucleotide on the transcripts. For each transcript, the array lists the transcript label and model outputs. The tool can output predictions using both the `npy` or `h5` format. 

```python
>>> results = np.load('results.npy', allow_pickle=True)
>>> results[0]
array(['>ENST00000410304',
       array([2.3891837e-09, 7.0824785e-07, 8.3791534e-09, 4.3269135e-09,
              4.9220684e-08, 1.5315813e-10, 7.0196869e-08, 2.4103475e-10,
              4.5873511e-10, 1.4299616e-10, 6.1071654e-09, 1.9664975e-08,
              2.9255699e-07, 4.7719610e-08, 7.7600065e-10, 9.2305236e-10,
              3.3297397e-07, 3.5771163e-07, 4.1942007e-05, 4.5123262e-08,
              1.0270607e-11, 1.1841109e-09, 7.9038587e-10, 6.5511790e-10,
              6.0892291e-13, 1.6157842e-11, 6.9130129e-10, 4.5778301e-11,
              2.1682500e-03, 2.3315516e-09, 2.2578116e-11], dtype=float32)],
      dtype=object)

```

### Other function flags
Various other function flags dictate the properties of the dataloader, model architecture and training procedure.

<details><summary>Dataloader</summary>

```
data loader arguments

  --min_seq_len int     minimum sequence length of transcripts (default: 0)
  --max_seq_len int     maximum sequence length of transcripts (default: 30000)
  --leaky_frac float    fraction of samples that escape conditions (default: 0.05)
  --num_workers int     number of data loader workers (default: 12)
  --max_transcripts_per_batch int
                        maximum of transcripts per batch (default: 400)
```

</details>

<details><summary>Model architecture</summary>

```
Model:
  Transformer arguments

  --transfer_checkpoint str
                        Path to checkpoint pretrained model (default: None)
  --lr float            learning rate (default: 0.001)
  --decay_rate float    linearly decays learning rate for every epoch (default: 0.95)
  --num_tokens int      number of unique input tokens (default: 7)
  --dim int             dimension of the hidden states (default: 30)
  --depth int           number of layers (default: 6)
  --heads int           number of attention heads in every layer (default: 6)
  --dim_head int        dimension of the attention head matrices (default: 16)
  --nb_features int     number of random features, if not set, will default to (d * log(d)),where d is the dimension
                        of each head (default: 80)
                        of each head (default: 80)
  --feature_redraw_interval int
                        how frequently to redraw the projection matrix (default: 100)
  --generalized_attention boolean
                        applies generalized attention functions (default: True)
  --kernel_fn boolean   generalized attention function to apply (if generalized attention) (default: ReLU())
  --reversible boolean  reversible layers, from Reformer paper (default: True)
  --ff_chunks int       chunk feedforward layer, from Reformer paper (default: 10)
  --use_scalenorm boolean
                        use scale norm, from 'Transformers without Tears' paper (default: False)
  --use_rezero boolean  use rezero, from 'Rezero is all you need' paper (default: False)
  --ff_glu boolean      use GLU variant for feedforward (default: True)
  --emb_dropout float   embedding dropout (default: 0.1)
  --ff_dropout float    feedforward dropout (default: 0.1)
  --attn_dropout float  post-attn dropout (default: 0.1)
  --local_attn_heads int
                        the amount of heads used for local attention (default: 4)
  --local_window_size int
                        window size of local attention (default: 256)
```

</details>

<details><summary>Pytorch lightning trainer</summary>

```
pl.Trainer:
  --logger [str_to_bool]
                        Logger (or iterable collection of loggers) for experiment tracking. A ``True`` value uses
                        the default ``TensorBoardLogger``. ``False`` will disable logging. (default: True)
  --checkpoint_callback [str_to_bool]
                        If ``True``, enable checkpointing. It will configure a default ModelCheckpoint callback if
                        there is no user-defined ModelCheckpoint in
                        :paramref:`~pytorch_lightning.trainer.trainer.Trainer.callbacks`. (default: True)
  --default_root_dir str
                        Default path for logs and weights when no logger/ckpt_callback passed. Default:
                        ``os.getcwd()``. Can be remote file paths such as `s3://mybucket/path` or 'hdfs://path/'
                        (default: None)
  --gradient_clip_val float
                        0 means don't clip. (default: 0.0)
  --gradient_clip_algorithm str
                        'value' means clip_by_value, 'norm' means clip_by_norm. Default: 'norm' (default: norm)
  --process_position int
                        orders the progress bar when running multiple models on same machine. (default: 0)
  --num_nodes int       number of GPU nodes for distributed training. (default: 1)
  --num_processes int   number of processes for distributed training with distributed_backend="ddp_cpu" (default: 1)
  --gpus _gpus_allowed_type
                        number of gpus to train on (int) or which GPUs to train on (list or str) applied per node
                        (default: None)
  --auto_select_gpus [str_to_bool]
                        If enabled and `gpus` is an integer, pick available gpus automatically. This is especially
                        useful when GPUs are configured to be in "exclusive mode", such that only one process at a
                        time can access them. (default: False)
  --tpu_cores _gpus_allowed_type
                        How many TPU cores to train on (1 or 8) / Single TPU to train on [1] (default: None)
  --log_gpu_memory str  None, 'min_max', 'all'. Might slow performance (default: None)
  --progress_bar_refresh_rate int
                        How often to refresh progress bar (in steps). Value ``0`` disables progress bar. Ignored
                        when a custom progress bar is passed to :paramref:`~Trainer.callbacks`. Default: None, means
                        a suitable value will be chosen based on the environment (terminal, Google COLAB, etc.).
                        (default: None)
  --overfit_batches _int_or_float_type
                        Overfit a fraction of training data (float) or a set number of batches (int). (default: 0.0)
  --track_grad_norm float
                        -1 no tracking. Otherwise tracks that p-norm. May be set to 'inf' infinity-norm. (default:
                        -1)
  --check_val_every_n_epoch int
                        Check val every n train epochs. (default: 1)
  --fast_dev_run [str_to_bool_or_int]
                        runs n if set to ``n`` (int) else 1 if set to ``True`` batch(es) of train, val and test to
                        find any bugs (ie: a sort of unit test). (default: False)
  --accumulate_grad_batches int
                        Accumulates grads every k batches or as set up in the dict. (default: 1)
  --max_epochs int      Stop training once this number of epochs is reached. Disabled by default (None). If both
                        max_epochs and max_steps are not specified, defaults to ``max_epochs`` = 1000. (default:
                        None)
  --min_epochs int      Force training for at least these many epochs. Disabled by default (None). If both
                        min_epochs and min_steps are not specified, defaults to ``min_epochs`` = 1. (default: None)
  --max_steps int       Stop training after this number of steps. Disabled by default (None). (default: None)
  --min_steps int       Force training for at least these number of steps. Disabled by default (None). (default:
                        None)
  --max_time str        Stop training after this amount of time has passed. Disabled by default (None). The time
                        duration can be specified in the format DD:HH:MM:SS (days, hours, minutes seconds), as a
                        :class:`datetime.timedelta`, or a dictionary with keys that will be passed to
                        :class:`datetime.timedelta`. (default: None)
  --limit_train_batches _int_or_float_type
                        How much of training dataset to check (float = fraction, int = num_batches) (default: 1.0)
  --limit_val_batches _int_or_float_type
                        How much of validation dataset to check (float = fraction, int = num_batches) (default: 1.0)
  --limit_test_batches _int_or_float_type
                        How much of test dataset to check (float = fraction, int = num_batches) (default: 1.0)
  --limit_predict_batches _int_or_float_type
                        How much of prediction dataset to check (float = fraction, int = num_batches) (default: 1.0)
  --val_check_interval _int_or_float_type
                        How often to check the validation set. Use float to check within a training epoch, use int
                        to check every n steps (batches). (default: 1.0)
  --flush_logs_every_n_steps int
                        How often to flush logs to disk (defaults to every 100 steps). (default: 100)
  --log_every_n_steps int
                        How often to log within steps (defaults to every 50 steps). (default: 50)
  --accelerator str     Previously known as distributed_backend (dp, ddp, ddp2, etc...). Can also take in an
                        accelerator object for custom hardware. (default: None)
  --sync_batchnorm [str_to_bool]
                        Synchronize batch norm layers between process groups/whole world. (default: False)
  --precision int       Double precision (64), full precision (32) or half precision (16). Can be used on CPU, GPU
                        or TPUs. (default: 32)
  --weights_summary str
                        Prints a summary of the weights when training begins. (default: top)
  --weights_save_path str
                        Where to save weights if specified. Will override default_root_dir for checkpoints only. Use
                        this if for whatever reason you need the checkpoints stored in a different place than the
                        logs written in `default_root_dir`. Can be remote file paths such as `s3://mybucket/path` or
                        'hdfs://path/' Defaults to `default_root_dir`. (default: None)
  --num_sanity_val_steps int
                        Sanity check runs n validation batches before starting the training routine. Set it to `-1`
                        to run all batches in all validation dataloaders. (default: 2)
  --truncated_bptt_steps int
                        Deprecated in v1.3 to be removed in 1.5. Please use
                        :paramref:`~pytorch_lightning.core.lightning.LightningModule.truncated_bptt_steps` instead.
                        (default: None)
  --resume_from_checkpoint str
                        Path/URL of the checkpoint from which training is resumed. If there is no checkpoint file at
                        the path, start from scratch. If resuming from mid-epoch checkpoint, training will start
                        from the beginning of the next epoch. (default: None)
  --profiler str        To profile individual steps during training and assist in identifying bottlenecks. (default:
                        None)
  --benchmark [str_to_bool]
                        If true enables cudnn.benchmark. (default: False)
  --deterministic [str_to_bool]
                        If true enables cudnn.deterministic. (default: False)
  --reload_dataloaders_every_epoch [str_to_bool]
                        Set to True to reload dataloaders every epoch. (default: False)
  --auto_lr_find [str_to_bool_or_str]
                        If set to True, will make trainer.tune() run a learning rate finder, trying to optimize
                        initial learning for faster convergence. trainer.tune() method will set the suggested
                        learning rate in self.lr or self.learning_rate in the LightningModule. To use a different
                        key set a string instead of True with the key name. (default: False)
  --replace_sampler_ddp [str_to_bool]
                        Explicitly enables or disables sampler replacement. If not specified this will toggled
                        automatically when DDP is used. By default it will add ``shuffle=True`` for train sampler
                        and ``shuffle=False`` for val/test sampler. If you want to customize it, you can set
                        ``replace_sampler_ddp=False`` and add your own distributed sampler. (default: True)
  --terminate_on_nan [str_to_bool]
                        If set to True, will terminate training (by raising a `ValueError`) at the end of each
                        training batch, if any of the parameters or the loss are NaN or +/-inf. (default: False)
  --auto_scale_batch_size [str_to_bool_or_str]
                        If set to True, will `initially` run a batch size finder trying to find the largest batch
                        size that fits into memory. The result will be stored in self.batch_size in the
                        LightningModule. Additionally, can be set to either `power` that estimates the batch size
                        through a power search or `binsearch` that estimates the batch size through a binary search.
                        (default: False)
  --prepare_data_per_node [str_to_bool]
                        If True, each LOCAL_RANK=0 will call prepare data. Otherwise only NODE_RANK=0, LOCAL_RANK=0
                        will prepare data (default: True)
  --plugins str         Plugins allow modification of core behavior like ddp and amp, and enable custom lightning
                        plugins. (default: None)
  --amp_backend str     The mixed precision backend to use ("native" or "apex") (default: native)
  --amp_level str       The optimization level to use (O1, O2, etc...). (default: O2)
  --distributed_backend str
                        deprecated. Please use 'accelerator' (default: None)
  --move_metrics_to_cpu [str_to_bool]
                        Whether to force internal logged metrics to be moved to cpu. This can save some gpu memory,
                        but can make training slower. Use with attention. (default: False)
  --multiple_trainloader_mode str
                        How to loop over the datasets when there are multiple train loaders. In 'max_size_cycle'
                        mode, the trainer ends one epoch when the largest dataset is traversed, and smaller datasets
                        reload when running out of their data. In 'min_size' mode, all the datasets reload when
                        reaching the minimum length of datasets. (default: max_size_cycle)
  --stochastic_weight_avg [str_to_bool]
                        Whether to use `Stochastic Weight Averaging (SWA)(default: False)
```

</details>


## ✔️ Package features

- [ ] creation of `h5` file from genome assemblies and ribosome profiling datasets
- [x] bucket sampling
- [x] pre-training functionality
- [x] data loading for sequence and ribosome data
- [x] custom target labels
- [ ] function hooks for custom data loading and pre-processing
- [x] model architectures
- [x] application of trained networks
- [ ] test scripts

## 🖊️ Citation <a name="citation"></a>
       
```latex
@article {Clauwaert2021.11.18.468957,
	author = {Clauwaert, Jim and McVey, Zahra and Gupta, Ramneek and Menschaert, Gerben},
	title = {TIS Transformer: Re-annotation of the human proteome using deep learning},
	elocation-id = {2021.11.18.468957},
	year = {2021},
	doi = {10.1101/2021.11.18.468957},
	URL = {https://www.biorxiv.org/content/early/2021/11/19/2021.11.18.468957},
	eprint = {https://www.biorxiv.org/content/early/2021/11/19/2021.11.18.468957.full.pdf},
	journal = {bioRxiv}
}
```
