```
b5mu@locutor5:~/interlocutor $ python3 interlocutor.py W%NYV --web-interface
Traceback (most recent call last):
  File "/home/kb5mu/interlocutor/interlocutor.py", line 89, in <module>
    import sounddevice
ModuleNotFoundError: No module named 'sounddevice'
kb5mu@locutor5:~/interlocutor $ pyenv --help
bash: pyenv: command not found
kb5mu@locutor5:~/interlocutor $ sudo apt install pyenv
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
E: Unable to locate package pyenv
kb5mu@locutor5:~/interlocutor $ 


   12  git clone https://github.com/OpenResearchInstitute/interlocutor
   13  cd interlocutor/
   14  ls
   15  python3 interlocutor.py W%NYV --web-interface


   23  curl https://pyenv.run | bash
   24  sudo nano ~/.bashrc

added:
# add pyenv to .bashrc
# this lets terminal know where to look for the pyenv
# versions of Python that we will be using. 
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"


   25  exec $SHELL

   26  sudo apt-get install --yes libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libgdbm-dev lzma lzma-dev tcl-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev wget curl make build-essential openssl
   27  pyenv update
   28  pyenv install --list
   29  cd interlocutor/
   30  cat requirements.txt 
   31  which python
   32  python3 --version
   34  pyenv virtualenv 3.11.2 orbital
   41  pyenv activate orbital

(orbital) kb5mu@locutor5:~/interlocutor $ 
(orbital) kb5mu@locutor5:~/interlocutor $ sudo apt install python3-pyaudio

    sudo apt install build-essential portaudio19-dev python3-dev

(orbital) kb5mu@locutor5:~/interlocutor $ pip3 install -r requirements.txt 





...
    Device.pin_factory = Device._default_pin_factory()
                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/kb5mu/.pyenv/versions/orbital/lib/python3.11/site-packages/gpiozero/devices.py", line 302, in _default_pin_factory
    raise BadPinFactory('Unable to load any default pin factory!')
gpiozero.exc.BadPinFactory: Unable to load any default pin factory!
Thank you for using Opulent Voice!

missing pin factory

(orbital) kb5mu@locutor5:~/interlocutor $ pip3 install lgpio

(orbital) kb5mu@locutor5:~/interlocutor $ pip3 install opuslib_next









```
