# Tutorial - User Guide { #tutorial-user-guide }

This tutorial shows you how to use **Logust** with most of its features, step by step.

Each section gradually builds on the previous ones, but it's structured to separate topics, so that you can go directly to any specific one to solve your specific logging needs.

It is also built to work as a future reference, so you can come back and see exactly what you need.

## Run the code { #run-the-code }

All the code blocks can be copied and used directly (they are actually tested Python files).

To run any of the examples, copy the code to a file `main.py`, and run it with Python:

<div class="termy">

```console
$ python main.py

<font color="#8A8A8A">2026-10-06 12:01:06.708</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">3</font> - Hello, Logust!
```

</div>

It is **HIGHLY encouraged** that you write or copy the code, edit it and run it locally.

Changing a format string, a level or a sink and seeing what happens is the fastest way to get a feel for how Logust works. 🤓

---

## Install Logust { #install-logust }

The first step is to install Logust.

Create a [virtual environment](https://docs.python.org/3/library/venv.html), activate it, and then install it:

//// tab | pip

<div class="termy">

```console
$ pip install logust

---> 100%

Successfully installed logust
```

</div>

////

//// tab | uv

<div class="termy">

```console
$ uv add logust

---> 100%
```

</div>

////

Logust has **no required dependencies**. The package ships pre-built wheels for **Linux**, **macOS** and **Windows**, so you don't need a Rust toolchain to install it.

/// info

Logust supports **Python 3.10** and above.

///

### Optional extras { #optional-extras }

Some integrations need a web framework. You can install it together with Logust using an **extra**:

//// tab | FastAPI

<div class="termy">

```console
$ pip install "logust[fastapi]"

---> 100%
```

</div>

////

//// tab | Starlette

<div class="termy">

```console
$ pip install "logust[starlette]"

---> 100%
```

</div>

////

These extras install the framework alongside Logust, so `logust.contrib.starlette` and its `RequestLoggerMiddleware` work out of the box. You will see them in action in [Use with FastAPI](../how-to/fastapi.md).

If you use `uv`, the same extras work with `uv add "logust[fastapi]"`.

### Build from source { #build-from-source }

If you want to hack on Logust itself (for example, to change the Rust core), you can build it from source with [maturin](https://www.maturin.rs/):

<div class="termy">

```console
$ git clone https://github.com/yamaaaaaa31/logust.git
$ cd logust
$ uv venv
$ source .venv/bin/activate
$ uv pip install maturin
$ maturin develop --release

---> 100%
```

</div>

/// note

Source builds need a stable **Rust** toolchain with `cargo`. You only need Rust for this: installing from PyPI never compiles anything.

On Windows, activate the environment with `.venv\Scripts\activate` instead.

///

### Check the installation { #check-the-installation }

To check that everything works, log a message straight from the command line:

<div class="termy">

```console
$ python -c "import logust; logust.info('Logust installed')"

<font color="#8A8A8A">2026-10-06 12:01:32.622</font> | <font color="#4E9A06"><b>INFO    </b></font> | <font color="#06989A">__main__</font>:<font color="#06989A">&lt;module&gt;</font>:<font color="#06989A">1</font> - Logust installed
```

</div>

If you see that line, you are ready to go. 🎉

## Advanced User Guide { #advanced-user-guide }

There is also an **Advanced User Guide** that you can read later after this **Tutorial - User Guide**.

The [Advanced User Guide](../advanced/index.md) builds on this one, uses the same concepts, and teaches you some extra features, like custom levels, `opt()`, background writes and performance tuning.

But you should first read the **Tutorial - User Guide** (what you are reading right now).

It's designed so that you can set up complete logging for an application with just the **Tutorial - User Guide**, and then extend it in different ways, depending on your needs, using some of the additional ideas from the **Advanced User Guide**.
