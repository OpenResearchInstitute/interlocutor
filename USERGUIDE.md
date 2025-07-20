```

12  git clone https://github.com/OpenResearchInstitute/interlocutor

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

recommended installations for pyenv: 
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
(orbital) kb5mu@locutor5:~/interlocutor $ pip3 install lgpio
(orbital) kb5mu@locutor5:~/interlocutor $ pip3 install opuslib_next





```
