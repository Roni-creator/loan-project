export default function Hero({ title, children }) {
  return (
    <header className="hero">
      <div className="wrap">
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
    </header>
  );
}
