from datetime import datetime

from sqlalchemy.orm import sessionmaker

from sphinx.websupport.comments import StorageBackend
from sphinx.websupport.comments.db import Base, Node, Comment, Vote

Session = sessionmaker()

class SQLAlchemyStorage(StorageBackend):
    def __init__(self, engine):
        self.engine = engine
        Base.metadata.bind = engine
        Base.metadata.create_all()
        Session.configure(bind=engine)

    def pre_build(self):
        self.build_session = Session()

    def add_node(self, document, line, source, treeloc):
        node = Node(document, line, source, treeloc)
        self.build_session.add(node)
        self.build_session.flush()
        return node.id

    def post_build(self):
        self.build_session.commit()
        self.build_session.close()

    def add_comment(self, parent_id, text, displayed, 
                    username, rating, time):
        time = time or datetime.now()
        
        session = Session()
        
        id = parent_id[1:]
        if parent_id[0] == 's':
            node = session.query(Node).filter(Node.id == id).first()
            comment = Comment(text, displayed, username, rating, 
                              time, node=node)
        elif parent_id[0] == 'c':
            parent = session.query(Comment).filter(Comment.id == id).first()
            comment = Comment(text, displayed, username, rating, 
                              time, parent=parent)
            
        session.add(comment)
        session.commit()
        comment = self.serializable(session, comment)
        session.close()
        return comment
        
    def get_comments(self, parent_id, user_id):
        parent_id = parent_id[1:]
        session = Session()
        node = session.query(Node).filter(Node.id == parent_id).first()
        comments = []
        for comment in node.comments:
            comments.append(self.serializable(session, comment, user_id))

        session.close()
        return comments

    def process_vote(self, comment_id, user_id, value):
        session = Session()
        vote = session.query(Vote).filter(
            Vote.comment_id == comment_id).filter(
            Vote.user_id == user_id).first()
        
        comment = session.query(Comment).filter(
            Comment.id == comment_id).first()

        if vote is None:
            vote = Vote(comment_id, user_id, value)
            comment.rating += value
        else:
            comment.rating += value - vote.value
            vote.value = value
        session.add(vote)
        session.commit()
        session.close()

    def serializable(self, session, comment, user_id=None):
        delta = datetime.now() - comment.time

        time = {'year': comment.time.year,
                'month': comment.time.month,
                'day': comment.time.day,
                'hour': comment.time.hour,
                'minute': comment.time.minute,
                'second': comment.time.second,
                'iso': comment.time.isoformat(),
                'delta': self.pretty_delta(delta)}

        vote = ''
        if user_id is not None:
            vote = session.query(Vote).filter(
                Vote.comment_id == comment.id).filter(
                Vote.user_id == user_id).first()
            if vote is not None:
                vote = vote.value 

        return {'text': comment.text,
                'username': comment.username or 'Anonymous',
                'id': comment.id,
                'rating': comment.rating,
                'age': delta.seconds,
                'time': time,
                'vote': vote or 0,
                'node': comment.node.id if comment.node else None,
                'parent': comment.parent.id if comment.parent else None,
                'children': [self.serializable(session, child, user_id) 
                             for child in comment.children]}

    def pretty_delta(self, delta):
        days = delta.days
        seconds = delta.seconds
        hours = seconds / 3600
        minutes = seconds / 60

        if days == 0:
            dt = (minutes, 'minute') if hours == 0 else (hours, 'hour')
        else:
            dt = (days, 'day')

        return '%s %s ago' % dt if dt[0] == 1 else '%s %ss ago' % dt
