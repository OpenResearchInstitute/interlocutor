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




Explain potential audio conflicts or mixing:



            <h4>🐧 Linux/Raspberry Pi Audio Notice</h4>
            <p><strong>Audio device exclusivity:</strong> Only one application can use each audio device at a time.</p>
            
            <div class="audio-recommendations">
                <h5>✅ Recommended Setup:</h5>
                <ul>
                    <li><strong>Radio:</strong> USB headset (selected in --setup-audio)</li>
                    <li><strong>Browser:</strong> HDMI/built-in speakers</li>
                </ul>
                
                <h5>⚠️ If using same device:</h5>
                <ul>
                    <li>Browser audio may stall when radio is active</li>
                    <li>Stop radio to release audio device for browser</li>
                    <li>Refresh browser tabs if audio doesn't resume</li>
                </ul>
            </div>

Provide a way to see what audio devices are selected

Provide a way to select audio devices from configuration screen

Maybe provide a device release/switching tools
function 
            <h3>🥧 Raspberry Pi Audio Guide</h3>
            
            <div class="audio-scenario">
                <h4>✅ Best Setup (No Conflicts)</h4>
                <p><strong>Radio:</strong> USB headset/microphone</p>
                <p><strong>Browser:</strong> HDMI output to monitor/TV</p>
                <p><em>Result: Both work simultaneously</em></p>
            </div>
            
            <div class="audio-scenario">
                <h4>⚠️ Shared Device Setup</h4>
                <p><strong>Both using same USB headset</strong></p>
                <p><em>Result: Only one app can use audio at a time</em></p>
                
                <h4>🔧 Hardware Solutions</h4>
                <ul>
                    <li><strong>Two USB devices:</strong> One for radio, one for computer</li>
                    <li><strong>USB hub with multiple audio:</strong> Separate devices</li>
                    <li><strong>3.5mm splitter:</strong> Share single headset between devices</li>
                </ul>
            </div>
        </div>
    `;
}


```
