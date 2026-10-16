const katex = require("katex");

let input = "";

process.stdin.setEncoding("utf8");

process.stdin.on("data", (chunk) => {
    input += chunk;

    if (input.length > 1_000_000) {
        process.stderr.write("Input is too large");
        process.exit(1);
    }
});

process.stdin.on("end", () => {
    try {
        const { tex, displayMode = false } = JSON.parse(input);

        if (
            typeof tex !== "string" ||
            tex.length === 0 ||
            tex.length > 10000
        ) {
            throw new Error("Invalid formula");
        }

        const html = katex.renderToString(tex, {
            displayMode: Boolean(displayMode),
            throwOnError: true,
            strict: "error",
            trust: false,
            output: "htmlAndMathml",
            maxExpand: 1000,
            maxSize: 20,
        });

        process.stdout.write(JSON.stringify({ html }));
    } catch (error) {
        process.stderr.write(String(error.message));
        process.exitCode = 1;
    }
})