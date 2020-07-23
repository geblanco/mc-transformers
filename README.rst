===============
mc_transformers
===============


.. image:: https://img.shields.io/pypi/v/mc_transformers.svg
        :target: https://pypi.python.org/pypi/mc_transformers

.. image:: https://img.shields.io/travis/geblanco/mc_transformers.svg
        :target: https://travis-ci.com/geblanco/mc_transformers

.. image:: https://readthedocs.org/projects/mc_transformers/badge/?version=latest
        :target: https://mc_transformers.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

Code to run experiments over Multiple Choice QA with huggingface/transformers.
A big part of the code comes from [huggingface/transformers](https://huggingface.co/transformers/), so its license may apply (Apache v2).

## Code
* `utils_mc.py`: Contains processors specific to each MC QA collection (RACE, SWAG, EntranceExams...)
* `run_mc_trainer.py`: Code to train/eval/test models over any collection with transfomers

## Why
As I experiment with more MC collection and training modes (i.e.: tpu), support for more collections or more models is required. Instead of forking the whole transformers library I do it here.


Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage