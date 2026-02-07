"""Entry point: python -m brief_analyzer"""

from .cli import parse_args
from .pipeline import run_pipeline
from .state import PipelineState


def main():
    config, args = parse_args()

    if args.status:
        state = PipelineState.load(config.state_file)
        print(state.summary())
        return

    run_pipeline(
        config,
        single_step=args.step,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
