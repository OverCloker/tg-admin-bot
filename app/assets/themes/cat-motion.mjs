// DOM/WebGL-independent locomotion: turn, walk, wind up, jump, land, settle.
import {catPhaseAdvance} from './cat-gait.mjs';
export class CatMotion {
  constructor(width,height,now=0) {
    this.size=180; this.resize(width,height); this.x=this.maxX; this.y=this.maxY;
    this.vx=this.vy=0; this.facing=1; this.heading=0; this.state='idle'; this.phase=0;
    this.started=this.lastInput=this.lastTick=now; this.look={x:width/2,y:height/2};
    this.move=this.goal=this.pending=null; this.pausedAt=null; this.reduced=false; this.returning=false;
  }
  resize(width,height) {
    this.width=Math.max(16,width); this.height=Math.max(16,height);
    this.size=Math.min(180,this.width-8,this.height-8);
    this.maxX=Math.max(4,this.width-this.size-4); this.maxY=Math.max(4,this.height-this.size-4);
    this.x=this.clampX(this.x??this.maxX); this.y=this.clampY(this.y??this.maxY);
    if(this.move){this.move.x=this.clampX(this.move.x);this.move.y=this.clampY(this.move.y);}
    if(this.goal){this.goal.x=this.clampX(this.goal.x);this.goal.y=this.clampY(this.goal.y);}
  }
  clampX(x){return Math.max(4,Math.min(this.maxX,x));}
  clampY(y){return Math.max(4,Math.min(this.maxY,y));}
  setState(state,now){this.state=state;this.started=now;}
  pause(now){if(this.pausedAt===null)this.pausedAt=now;}
  resume(now){
    if(this.pausedAt!==null){const d=now-this.pausedAt;this.started+=d;this.lastInput+=d;
      if(this.move)this.move.start+=d;this.pausedAt=null;}
    this.lastTick=now;
  }
  tap(x,y,now){
    this.lastInput=now;this.look={x,y};
    if(!this.reduced&&['leaping','landing','settling','sitting','sleeping','curling','waking'].includes(this.state)){
      this.pending={x,y};
      if(['sitting','sleeping','curling'].includes(this.state))this.setState('waking',now);
      return;
    }
    this.follow(x,y,now);
  }
  follow(x,y,now){
    this.returning=false;
    const facing=x<this.x+this.size/2?-1:1;
    this.goal={x:this.clampX(x-this.size*(facing>0?.73:.27)),y:this.clampY(y-this.size*.7)};
    if(this.reduced){this.move=null;this.vx=this.vy=0;this.facing=facing;this.setState('watching',now);return;}
    const turning=facing!==this.facing;
    const previousFacing=this.facing;
    this.facing=facing;
    if(turning)this.startTurn(now,previousFacing);
    else this.startWalk(now);
  }
  startTurn(now,previousFacing){
    this.setState('turning',now);
    const x=this.clampX(this.x+this.facing*36);
    this.moveTo(x,this.y,now,'turn');
    // A short walking arc, with room for the forequarters to lead the turn.
    const m=this.move;
    m.c1={x:this.clampX(this.x+previousFacing*18),y:this.clampY(this.y-24)};
    m.c2={x:this.clampX(x-this.facing*18),y:this.clampY(this.y-24)};
  }
  startWalk(now){
    if(!this.goal)return;
    const vertical=Math.abs(this.goal.y-this.y)>50;
    const dx=this.goal.x-this.x;
    // Walk towards a take-off point; do not glide diagonally to a high control.
    const runway=vertical?Math.min(90,Math.abs(dx)*.35):0;
    const x=this.clampX(this.goal.x-Math.sign(dx)*runway);
    if(Math.abs(x-this.x)>12){
      this.setState(this.returning?'going-home':'approaching',now);
      this.moveTo(x,this.y,now,'walk');
    } else this.prepareArrival(now);
  }
  prepareArrival(now){
    if(Math.abs(this.goal.y-this.y)>50||Math.abs(this.goal.x-this.x)>15)this.setState('crouching',now);
    else this.arrive(now);
  }
  arrive(now){
    this.move=null;this.vx=this.vy=0;
    if(this.pending){const tap=this.pending;this.pending=null;this.follow(tap.x,tap.y,now);}
    else this.settle(now);
  }
  settle(now){
    if(this.reduced){this.heading=0;this.setState(this.returning?'sleeping':'sitting',now);return;}
    this.setState('settling',now);
    const dx=this.x>this.width/2?-20:20;
    this.moveTo(this.clampX(this.x+dx),this.clampY(this.y+8),now,'settle');
    const m=this.move;
    m.c1={x:this.clampX(this.x+Math.sin(this.heading)*16),y:this.clampY(this.y+Math.cos(this.heading)*16)};
    m.c2={x:m.x,y:this.clampY(m.y-18)};
  }
  moveTo(x,y,now,type){
    const distance=Math.hypot(x-this.x,y-this.y);
    this.move={fromX:this.x,fromY:this.y,x,y,start:now,type,
      duration:['turn','settle'].includes(type)?1050:type==='jump'?Math.min(1400,780+Math.abs(y-this.y)*.7):Math.max(450,Math.min(8000,distance*12)),
      vx:this.vx,vy:this.vy,arc:type==='jump'?Math.min(100,35+distance*.12):0};
  }
  home(now){
    this.pending=null;this.returning=true;
    this.goal={x:this.x+this.size/2<this.width/2?4:this.maxX,y:this.maxY};
    const previousFacing=this.facing;
    this.facing=this.goal.x<this.x?-1:1;
    if(this.reduced){this.x=this.goal.x;this.y=this.maxY;this.move=null;this.setState('sleeping',now);return;}
    if(previousFacing!==this.facing)this.startTurn(now,previousFacing);else this.startWalk(now);
  }
  step(now){
    if(this.pausedAt!==null)return this.snapshot(now);
    const oldX=this.x,oldY=this.y;this.lastTick=now;
    if(this.move){
      const m=this.move,p=Math.max(0,Math.min(1,(now-m.start)/m.duration));
      if(['turn','settle'].includes(m.type)){
        const q=1-p;
        this.x=this.clampX(q*q*q*m.fromX+3*q*q*p*m.c1.x+3*q*p*p*m.c2.x+p*p*p*m.x);
        this.y=this.clampY(q*q*q*m.fromY+3*q*q*p*m.c1.y+3*q*p*p*m.c2.y+p*p*p*m.y);
        this.vx=(3*q*q*(m.c1.x-m.fromX)+6*q*p*(m.c2.x-m.c1.x)+3*p*p*(m.x-m.c2.x))/m.duration;
        this.vy=(3*q*q*(m.c1.y-m.fromY)+6*q*p*(m.c2.y-m.c1.y)+3*p*p*(m.y-m.c2.y))/m.duration;
      }else if(m.type==='jump'){
        this.x=this.clampX(m.fromX+(m.x-m.fromX)*p);
        this.y=this.clampY(m.fromY+(m.y-m.fromY)*p-m.arc*4*p*(1-p));
        this.vx=(m.x-m.fromX)/m.duration;this.vy=((m.y-m.fromY)-m.arc*4*(1-2*p))/m.duration;
      }else{
        const e=p*p*(3-2*p),h=p*(1-p)**2;
        this.x=this.clampX(m.fromX+(m.x-m.fromX)*e+m.vx*m.duration*h);
        this.y=this.clampY(m.fromY+(m.y-m.fromY)*e+m.vy*m.duration*h);
        this.vx=(m.x-m.fromX)*6*p*(1-p)/m.duration+m.vx*(1-4*p+3*p*p);
        this.vy=(m.y-m.fromY)*6*p*(1-p)/m.duration+m.vy*(1-4*p+3*p*p);
      }
      if(p>=1){this.move=null;this.vx=this.vy=0;
        if(m.type==='jump')this.setState('landing',now);
        else if(m.type==='turn')this.startWalk(now);
        else if(m.type==='settle'){this.heading=0;
          if(this.pending){const tap=this.pending;this.pending=null;this.follow(tap.x,tap.y,now);}
          else this.setState(this.returning?'curling':'sitting',now);}
        else this.prepareArrival(now);}
    }
    const age=now-this.started;
    if(this.state==='crouching'&&age>=280){this.setState('leaping',now);this.moveTo(this.goal.x,this.goal.y,now,'jump');}
    else if(this.state==='landing'&&age>=360)this.arrive(now);
    else if(this.state==='waking'&&age>=850){
      const tap=this.pending;this.pending=null;if(tap)this.follow(tap.x,tap.y,now);else this.setState('idle',now);
    }else if(this.state==='curling'&&age>=1800)this.setState('sleeping',now);
    else if(this.state==='reaching'&&age>=4200)this.setState('watching',now);
    else if(this.state==='watching'&&age>=4200)this.setState('idle',now);
    if(now-this.lastInput>=18000&&!this.returning&&!['sleeping','curling'].includes(this.state))this.home(now);
    if(['turning','settling','approaching','going-home'].includes(this.state)){
      const distance=Math.hypot(this.x-oldX,this.y-oldY);
      this.phase+=catPhaseAdvance(distance,this.size);
      if(distance>.001)this.heading=Math.atan2(this.x-oldX,this.y-oldY);
    }
    return this.snapshot(now);
  }
  snapshot(now){
    return {x:this.x,y:this.y,size:this.size,state:this.state,facing:this.facing,heading:this.heading,speed:Math.hypot(this.vx,this.vy),
      age:Math.max(0,now-this.started),look:this.look,phase:this.phase,reduced:this.reduced,time:now/1000,
      flight:this.move?.type==='jump'?Math.min(1,(now-this.move.start)/this.move.duration):0};
  }
}
