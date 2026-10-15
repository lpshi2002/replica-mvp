import {Composition} from 'remotion';
import {ReplicaLaunch, TOTAL_FRAMES} from './ReplicaLaunch';
import {ReplicaLaunchV2, TOTAL_FRAMES_V2} from './ReplicaLaunchV2';
import {ReplicaLaunchV3, TOTAL_FRAMES_V3} from './ReplicaLaunchV3';

export const RemotionRoot = () => (
  <>
    <Composition id="ReplicaLaunch" component={ReplicaLaunch} durationInFrames={TOTAL_FRAMES} fps={30} width={1920} height={1080} />
    <Composition id="ReplicaLaunchV2" component={ReplicaLaunchV2} durationInFrames={TOTAL_FRAMES_V2} fps={30} width={1920} height={1080} />
    <Composition id="ReplicaLaunchV3" component={ReplicaLaunchV3} durationInFrames={TOTAL_FRAMES_V3} fps={30} width={1920} height={1080} />
  </>
);
