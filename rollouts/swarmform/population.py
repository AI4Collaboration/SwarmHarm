"""Population parameters shared by input builders and runtimes, without a size menu."""


def validate(population, *, minimum=1):
    if type(population) is not int or population < minimum:
        raise ValueError(f'Population must be an integer >= {minimum}')
    return population


def research_actors(population=8):
    return tuple(f'Research{i:02d}' for i in range(1, validate(population)+1))


def business_actors(defaults, population=3):
    validate(population)
    return tuple(defaults[:population]) + tuple(
        f'Office{i:06d}' for i in range(len(defaults)+1, population+1))


def count_text(population):
    """Keep the established eight-actor prompt bytes at their original scale."""
    validate(population)
    return 'eight' if population == 8 else str(population)


def account_ids(population):
    """Distinct business users, avoiding the shared delivery group and nobody."""
    validate(population)
    result, value = [], 62000
    while len(result) < population:
        if value not in (63000, 65534):
            result.append(value)
        value += 1
    return result


def unique_number(preferred, used, *, lower, upper):
    """Resolve identifier collisions deterministically within the carrier's format."""
    value = preferred
    while value in used:
        value = lower + (value-lower+1) % (upper-lower+1)
        if value == preferred:
            raise ValueError('Carrier identifier space exhausted')
    return value
