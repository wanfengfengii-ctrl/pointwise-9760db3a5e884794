from gallery.routes.proofs import RouteProof, get_proof


class UnknownProof(LookupError):
    pass


class UnreachableProof(ValueError):
    pass


def require_issuable_proof(connection, proof_id: int) -> RouteProof:
    proof = get_proof(connection, proof_id)
    if proof is None:
        raise UnknownProof(f'没有校样 {proof_id}。')
    if proof.itinerary is None:
        raise UnreachableProof(f'校样 {proof_id} 不可达，无法发行。')
    return proof
