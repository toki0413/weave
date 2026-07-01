// ============ STATE ============
const state = {
  view: 'elderly',
  currentDay: 0,
  fontScale: 1,
  voiceFeedback: true,
  nodes: [],
  edges: [],
  nodeIdCounter: 0,
  selectedNode: null,
  selectedEdgeType: 'emotion',
  daySnapshots: {},
  baselineMetrics: null,
  dragging: null,
  dragOffset: { x: 0, y: 0 },
  animRunning: false,
  animFrame: 0,
  convergeCount: 0,
  anomalies: [],
  welcomeDismissed: false,
  svgW: 800,
  svgH: 500,
  historyStack: [],
  historyIndex: -1,
  sessionHistory: [],
  trendWindow: 30,
  guidedMode: true,
  sttAvailable: true,
  lastAudioMetrics: null,
  trainingScores: [],
  lastEmotion: null,
};

const STATE_VERSION = 1;

const SCENARIOS = [
  { day: 1, label: '建立基准', status: 'ok', text: '今天在公园碰见老张，我们一起打太极，然后去超市买了菜，回家做了饭' },
  { day: 2, label: '基准完善', status: 'ok', text: '早上在家吃了药，老伴陪我去医院看张医生，量了血压，然后去药店买了药' },
  { day: 3, label: '正常波动', status: 'ok', text: '下午在客厅看报纸，孙子来看我，我们一起聊天看电视，很开心' },
  { day: 4, label: '正常生活', status: 'ok', text: '今天去菜市场买菜，碰见邻居王阿姨，聊了一会儿天，然后回家做饭' },
  { day: 5, label: '首个偏移', status: 'warn', text: '早上在公园晨练，老张没来，我一个人打了太极剑，然后回家做饭' },
  { day: 6, label: '匿名节点', status: 'warn', text: '今天在公园碰见那个打太极的、穿红衣服的，我们一起聊了天，然后去超市' },
  { day: 7, label: '关系错置', status: 'danger', text: '今天去医院碰见老张，他在打太极，然后我们一起去药房买药' },
];

const NODE_TYPES = {
  person: { color: '#4A7C4A', label: '人物', icon: '人' },
  place:  { color: '#B86B4C', label: '地点', icon: '地' },
  event:  { color: '#3D6FA8', label: '事件', icon: '事' },
  item:   { color: '#7B5394', label: '物品', icon: '物' },
  self:   { color: '#2D5A2C', label: '自我', icon: '我' },
  anon:   { color: '#B8860B', label: '匿名', icon: '?' },
};

const EDGE_TYPES = {
  emotion: { color: '#4A7C4A', width: 3, dash: 'none', label: '情感' },
  time:    { color: '#3D6FA8', width: 2, dash: '6,3', label: '时间' },
  space:   { color: '#B86B4C', width: 2, dash: '2,3', label: '空间' },
  custom:  { color: '#837A6E', width: 1.5, dash: 'none', label: '关联' },
};

const zoomPan = { scale: 1, panX: 0, panY: 0, isPanning: false, panStart: { x: 0, y: 0 } };

export function createStore(initialState) {
  var _state = Object.assign({}, initialState);
  var _listeners = new Set();

  function getState() {
    return _state;
  }

  function setState(partial) {
    _state = Object.assign({}, _state, partial);
    _listeners.forEach(function(fn) { fn(_state); });
  }

  function subscribe(fn) {
    _listeners.add(fn);
    return function() { _listeners.delete(fn); };
  }

  function dispatch(action) {
    switch (action.type) {
      case 'SET_VIEW':
        setState({ view: action.payload });
        break;
      case 'SELECT_NODE':
        setState({ selectedNode: action.payload });
        break;
      case 'SET_DAY':
        setState({ currentDay: action.payload });
        break;
      case 'SET_NODES':
        setState({ nodes: action.payload });
        break;
      case 'SET_EDGES':
        setState({ edges: action.payload });
        break;
      case 'SET_WELCOME':
        setState({ welcomeDismissed: action.payload });
        break;
      case 'SET_BASELINE':
        setState({ baselineMetrics: action.payload });
        break;
      case 'SET_FONT_SCALE':
        setState({ fontScale: action.payload });
        break;
      case 'SET_GUIDED_MODE':
        setState({ guidedMode: action.payload });
        break;
      case 'SET_SNAPSHOTS':
        setState({ daySnapshots: action.payload });
        break;
      default:
        setState(action.payload || {});
    }
  }

  return { getState, setState, subscribe, dispatch };
}

export { state, SCENARIOS, NODE_TYPES, EDGE_TYPES, zoomPan, STATE_VERSION };
