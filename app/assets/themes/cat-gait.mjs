// Inverse bind-world quaternion applied to the model's transverse X hinge axis.
export function modelXInBoneSpace([x,y,z,w]) {
  return [1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)];
}

const wrap = a => Math.atan2(Math.sin(a),Math.cos(a));
export const CAT_STRIDE=.12, CAT_CONTACT=.52, CAT_VIEW_SPAN=1.44/1.3;
export function catPhaseAdvance(distance,size) {
  // During contact the paw travels one stride while the body moves the same
  // distance. Account for the actual orthographic projection, not overlay size.
  return distance/(size*(CAT_STRIDE/CAT_CONTACT)/CAT_VIEW_SPAN)*Math.PI*2;
}
export function solveCatLeg(hip,knee,foot,phase,weight,target=foot) {
  const a=Math.atan2(knee[1]-hip[1],knee[0]-hip[0]);
  const b=Math.atan2(foot[1]-knee[1],foot[0]-knee[0]);
  const l1=Math.hypot(knee[0]-hip[0],knee[1]-hip[1]);
  const l2=Math.hypot(foot[0]-knee[0],foot[1]-knee[1]);
  const u=((phase/(Math.PI*2))%1+1)%1;
  const contact=CAT_CONTACT, swing=u>contact, p=swing?(u-contact)/(1-contact):u/contact;
  // Light trot: diagonal pairs alternate, with a short overlap for soft support.
  // Wider stride; position and velocity remain continuous at toe-off/contact.
  const stride=CAT_STRIDE, tangent=-stride*(1-contact)/contact;
  const offset=swing?-stride/2+stride*p*p*(3-2*p)+tangent*(2*p*p*p-3*p*p+p):stride/2-stride*p;
  const lift=swing?.042*Math.sin(Math.PI*p)**2:0;
  // No permanent foot lift: stance feet stay on the floor, not in a crouch.
  const limit=l1+l2-.00001,soft=.003;
  const dy=Math.max(-limit,Math.min(limit,target[0]-hip[0]+weight*lift));
  const requestedZ=target[1]-hip[1]+weight*offset;
  // Ease into anatomical reach instead of snapping the knee straight at the
  // wider stride endpoint. Shorten only horizontal reach: do not lift a planted
  // paw off the floor just because the requested stride exceeds leg length.
  const maxZ=Math.sqrt(Math.max(0,limit*limit-dy*dy)),zone=Math.min(soft,maxZ);
  const absZ=Math.abs(requestedZ),cappedZ=zone>0&&absZ>maxZ-zone?
    maxZ-zone*Math.exp(-(absZ-maxZ+zone)/zone):Math.min(absZ,maxZ);
  const dz=Math.sign(requestedZ)*cappedZ,requestedDistance=Math.hypot(dy,dz);
  const distance=Math.max(Math.abs(l1-l2)+.00001,requestedDistance);
  const clamp=v=>Math.max(-1,Math.min(1,v));
  const branch=Math.sign(wrap(b-a))||1;
  const theta=Math.atan2(dz,dy)-branch*Math.acos(clamp((l1*l1+distance*distance-l2*l2)/(2*l1*distance)));
  const bend=branch*Math.acos(clamp((distance*distance-l1*l1-l2*l2)/(2*l1*l2)));
  const hipTurn=wrap(theta-a), kneeTurn=wrap(bend-wrap(b-a));
  return {hip:hipTurn,knee:kneeTurn,wrist:-hipTurn-kneeTurn,lift:weight*lift,offset:weight*offset,swing,
    toeRoll:swing?-.18*weight*Math.sin(Math.PI*p):0,
    target:[hip[0]+dy*distance/Math.max(1e-9,requestedDistance),hip[1]+dz*distance/Math.max(1e-9,requestedDistance)]};
}

// Small vertical weight transfer, with critically damped suspension. Body height
// is applied BEFORE foot IK so grounded paws compensate instead of floating.
export function catSuspension(phase,weight) {
  return weight*(.0015+.0015*Math.cos(phase*2));
}
export function dampCatBody(value,velocity,target,dt) {
  const omega=16, step=Math.max(0,Math.min(.064,dt));
  const displacement=value-target, c=velocity+omega*displacement;
  const decay=Math.exp(-omega*step);
  return {value:target+(displacement+c*step)*decay,
    velocity:(velocity-omega*c*step)*decay};
}
