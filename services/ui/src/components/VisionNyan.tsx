const RAINBOW_COLORS = ['#ff3864', '#ff9f1c', '#f6f930', '#52ffb8', '#18a0fb', '#a364ff'];

const VisionNyan = () => (
  <div className="nyan-runner" aria-hidden="true">
    <div className="nyan-rainbow">
      {RAINBOW_COLORS.map((color, idx) => (
        <span key={color} style={{ backgroundColor: color, animationDelay: `${idx * 40}ms` }} />
      ))}
    </div>
    <div className="nyan-sprite">
      <div className="nyan-body">
        <span className="sprinkle sprinkle-a" />
        <span className="sprinkle sprinkle-b" />
        <span className="sprinkle sprinkle-c" />
      </div>
      <div className="nyan-head">
        <span className="ear ear-left" />
        <span className="ear ear-right" />
        <span className="eye eye-left" />
        <span className="eye eye-right" />
        <span className="cheek" />
      </div>
      <div className="nyan-tail" />
      <div className="nyan-legs">
        <span />
        <span />
      </div>
    </div>
  </div>
);

export default VisionNyan;
