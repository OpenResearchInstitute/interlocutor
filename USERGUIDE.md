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










### Reconnection behavior:
Current Reconnection Behavior

Initial reconnection attempts:

First retry: 1 second delay
Subsequent retries: Delay increases by 1.5x each time (exponential backoff)
Maximum delay: 30 seconds
Maximum attempts: 10 attempts
Total time before giving up: About 2-3 minutes

Specific Timing
```
let reconnectDelay = 1000; // Start with 1 second
let maxReconnectAttempts = 10;

// After each failed attempt:
reconnectDelay = Math.min(reconnectDelay * 1.5, 30000); // Max 30 seconds
```
Retry sequence:

1 second
1.5 seconds
2.25 seconds
3.4 seconds
5.1 seconds
7.6 seconds
11.4 seconds
17.1 seconds
25.6 seconds
30 seconds (max reached)

After 10 failed attempts: Shows "Connection failed - maximum retry attempts reached" and displays a manual retry button.
Manual Recovery Options

Manual Retry Button: Appears when auto-retry gives up
Page Visibility: If you switch browser tabs and come back, it will attempt to reconnect
Manual Refresh: Browser refresh will restart the connection process

Connection Timeout
Each individual connection attempt has a 5-second timeout before being considered failed.
So in total, if the radio system goes down, the web interface will:

Try for about 2-3 minutes to reconnect automatically
Then require manual intervention (retry button or page refresh)
Each connection attempt times out after 5 seconds

