#!/usr/bin/env python3
"""Cat's GB emulator with automatic dependency setup.
Run: python test.py [rom.gb]
Requires internet access to install missing PyBoy/Pillow dependencies.
"""
import argparse, io, pathlib, time, tkinter as tk
import importlib.util, subprocess, sys
from tkinter import filedialog, messagebox
FPS=59.7275

def ensure_dependencies():
    """Install missing packages into the active Python environment, or fail clearly."""
    missing = [package for module, package in (("pyboy", "pyboy"), ("PIL", "pillow"))
               if importlib.util.find_spec(module) is None]
    if not missing:
        return
    print("BenchCat: installing missing dependencies:", ", ".join(missing), flush=True)
    cmd = [sys.executable, "-m", "pip", "install", *missing]
    try:
        subprocess.check_call(cmd)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Dependency installation failed. Try: " + " ".join(cmd)) from exc
    importlib.invalidate_caches()
    still_missing = [name for name in ("pyboy", "PIL") if importlib.util.find_spec(name) is None]
    if still_missing:
        raise RuntimeError("Dependencies still missing: " + ", ".join(still_missing))

def deps():
    from pyboy import PyBoy
    from PIL import Image, ImageTk
    return PyBoy, Image, ImageTk

def core_open(path, sound=False):
    PyBoy,_,_=deps()
    try:return PyBoy(str(path),window='null',sound_emulated=sound,sound_volume=100 if sound else 0)
    except TypeError:return PyBoy(str(path),window_type='headless',sound=sound)

def core_close(core):
    if core:
        try:core.stop(save=False)
        except TypeError:core.stop()

class App:
    def __init__(self,root,path=None):
        self.r=root;self.core=None;self.path=None;self.state=None
        self.paused=False;self.audio=False;self.speed=1;self.scale=2;self.nearest=True
        self.keys=set();self.image=None;self.item=None;self.frames=0
        self.start=self.next=time.perf_counter();self.alive=True
        self.mapping={'Up':'up','Down':'down','Left':'left','Right':'right','z':'a','x':'b','Return':'start','BackSpace':'select','Shift_R':'select'}
        root.title('Cat\'s GB Emulator | BenchCat');root.geometry('600x400');root.resizable(False,False)
        bar=tk.Frame(root);bar.pack(fill='x')
        for name,cb in [('Open',self.open_dialog),('Pause',self.pause),('Reset',self.reset),('Save',self.save),('Load',self.restore),('Speed',self.speed_cycle),('Audio',self.audio_toggle),('Screenshot',self.screenshot)]:
            tk.Button(bar,text=name,command=cb).pack(side='left')
        self.canvas=tk.Canvas(root,bg='#151a28',highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        self.canvas.create_text(300,150,text='Open a .gb / .gbc ROM',fill='#9bbcff',font=('Helvetica',16))
        self.status=tk.StringVar(value='Ready');tk.Label(root,textvariable=self.status,anchor='w').pack(fill='x')
        root.bind('<KeyPress>',self.key_down);root.bind('<KeyRelease>',self.key_up)
        for hotkey,cb in [('<Control-o>',self.open_dialog),('<Control-r>',self.reset),('<F5>',self.save),('<F8>',self.restore),('<F12>',self.screenshot)]:root.bind(hotkey,lambda e,fn=cb:fn())
        root.protocol('WM_DELETE_WINDOW',self.close)
        if path:self.load(path)
        root.after(1,self.tick)
    def open_dialog(self):
        p=filedialog.askopenfilename(filetypes=[('Game Boy ROM','*.gb *.gbc *.rom')]);
        if p:self.load(p)
    def load(self,path):
        try:
            if pathlib.Path(path).stat().st_size<0x150:raise ValueError('ROM header missing')
            new=core_open(path,self.audio);new.set_emulation_speed(0)
        except Exception as e:messagebox.showerror('Load error',str(e));return
        core_close(self.core);self.core=new;self.path=path;self.state=None;self.keys.clear();self.paused=False
        self.frames=0;self.start=self.next=time.perf_counter();self.canvas.delete('all');self.item=None
        self.status.set('Loaded '+pathlib.Path(path).name)
    def tick(self):
        if not self.alive:return
        if self.core and not self.paused:
            try:
                n=2 if self.speed==2 else 1
                for _ in range(n):self.core.tick()
                self.frames+=n;self.render()
                now=time.perf_counter()
                if now-self.start>=0.7:
                    self.status.set(f'{self.frames/(now-self.start):.1f} emulated FPS | {self.speed}x | Audio {self.audio}')
                    self.frames=0;self.start=now
            except Exception as e:self.status.set('Error: '+str(e));core_close(self.core);self.core=None
        if not self.core or self.paused:delay=30;self.next=time.perf_counter()
        elif self.speed==0:delay=1
        else:
            interval=1/(FPS*(2 if self.speed==2 else 1));self.next+=interval
            now=time.perf_counter()
            if self.next<now-3*interval:self.next=now
            delay=max(1,int((self.next-now)*1000))
        self.r.after(delay,self.tick)
    def render(self):
        _,Image,ImageTk=deps();im=self.core.screen.image
        if im is None:return
        mode=Image.Resampling.NEAREST if self.nearest else Image.Resampling.BILINEAR
        self.image=ImageTk.PhotoImage(im.resize((160*self.scale,144*self.scale),mode))
        x,y=self.canvas.winfo_width()//2,self.canvas.winfo_height()//2
        if self.item is None:self.item=self.canvas.create_image(x,y,image=self.image)
        else:self.canvas.coords(self.item,x,y);self.canvas.itemconfigure(self.item,image=self.image)
    def key_down(self,e):
        key=self.mapping.get(e.keysym) or self.mapping.get(e.keysym.lower())
        if key and self.core and not self.paused and key not in self.keys:self.core.button_press(key);self.keys.add(key)
    def key_up(self,e):
        key=self.mapping.get(e.keysym) or self.mapping.get(e.keysym.lower())
        if key and self.core and key in self.keys:self.core.button_release(key);self.keys.remove(key)
    def pause(self):
        if self.core:
            self.paused=not self.paused
            if self.paused:
                for k in self.keys:self.core.button_release(k)
                self.keys.clear()
            self.next=time.perf_counter();self.status.set('Paused' if self.paused else 'Running')
    def reset(self):
        if self.path:self.load(self.path)
    def speed_cycle(self):self.speed={1:2,2:0,0:1}[self.speed];self.next=time.perf_counter();self.status.set('Speed '+str(self.speed))
    def audio_toggle(self):
        self.audio=not self.audio
        self.status.set('Audio setting changed; press Reset to apply')
    def save(self):
        if self.core:
            try:b=io.BytesIO();self.core.save_state(b);self.state=b.getvalue();self.status.set('State saved in RAM')
            except Exception as e:messagebox.showerror('Save error',str(e))
    def restore(self):
        if self.core and self.state:
            try:self.core.load_state(io.BytesIO(self.state));self.status.set('State loaded')
            except Exception as e:messagebox.showerror('Load error',str(e))
    def screenshot(self):
        if self.core:
            p=filedialog.asksaveasfilename(defaultextension='.png',filetypes=[('PNG','*.png')])
            if p:self.core.screen.image.save(p)
    def close(self):self.alive=False;core_close(self.core);self.r.destroy()

def main():
    parser = argparse.ArgumentParser(description="Cat's GB Emulator")
    parser.add_argument('rom', nargs='?', default=str(pathlib.Path(__file__).with_name('test.gb')))
    args = parser.parse_args()
    try:
        ensure_dependencies()
        deps()
    except (RuntimeError, ImportError) as exc:
        print(f'Dependency error: {exc}', file=sys.stderr)
        return 2
    root = tk.Tk()
    App(root, args.rom if pathlib.Path(args.rom).exists() else None)
    root.mainloop()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
