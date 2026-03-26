def detect_gaps(match_results):

    present = []
    missing = []

    THRESHOLD = 0.6

    for item in match_results:
        score = item["score"]

        if score >= THRESHOLD:
            present.append(item["clause"])
        else:
            missing.append(item["clause"])

    return present, missing