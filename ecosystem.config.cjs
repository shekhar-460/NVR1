module.exports = {
  apps: [
    {
      name: "nvr",
      cwd: "/home/ai_1/Desktop/SVELTE_EYE/NVR1",
      script: ".venv/bin/python3",
      args: ["-m", "nvr"],
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
